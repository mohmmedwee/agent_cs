"""The agent loop.

Call the model; if the reply carries tool calls, run them, append the results as
`role: tool` messages, and call again. Stop when a reply has no tool calls, or
after `max_steps` rounds.
"""

from collections.abc import AsyncIterator
from datetime import datetime
import json
import logging
from typing import Any
from uuid import UUID, uuid4

import httpx

from agent_console.clients.upstream import UpstreamClient, UpstreamError
from agent_console.config import Settings
from agent_console.models.chat import build_tool_message
from agent_console.repositories.files import FileRepository
from agent_console.repositories.memory import MemoryRepository
from agent_console.repositories.skill_catalog import SkillCatalog
from agent_console.repositories.skills import UnknownSkillError
from agent_console.models.events import (
    AgentEvent,
    DoneEvent,
    ErrorEvent,
    ReasoningDeltaEvent,
    TextDeltaEvent,
    ToolApprovalEvent,
    ToolCallDeltaEvent,
    ToolCallEvent,
    ToolResultEvent,
)
from agent_console.services.approvals import ApprovalBroker
from agent_console.services.runaway import is_runaway_repetition, trim_runaway_tail
from agent_console.services.tools import ToolRegistry
from agent_console.services.tools.edit_docx import (
    apply_edit_docx_payload,
    prepare_edit_docx_approval,
)
from agent_console.services.docx_soak import SoakTracker

__all__ = ["AgentService"]

logger = logging.getLogger(__name__)

# Loading a skill / listing / searching files is setup, not progress toward
# finishing the user's task — so those rounds do not spend the step budget.
# Without this, a long docx edit burns the whole budget on exploration and
# never reaches write_file.
_SETUP_TOOLS = frozenset(
    {
        "read_skill",
        "list_uploaded_files",
        "search_uploaded_files",
        "ask_user",
    }
)
# Extra loop iterations so free setup rounds still fit under the ceiling.
_SETUP_ALLOWANCE = 12


def _preview(text: str, limit: int = 160) -> str:
    flat = " ".join((text or "").split())
    if len(flat) <= limit:
        return flat
    return f"{flat[:limit]}…"


def _downgrade_effort(effort: str | None) -> str:
    """Next-lower reasoning effort after an empty completion.

    Qwen3.8 only knows low / medium / xhigh. High effort often spends the
    entire max_tokens on thinking; dropping effort on retry leaves budget
    for the actual tool call.
    """
    order = ("xhigh", "medium", "low", "minimal")
    current = (effort or "xhigh").lower().replace("x-high", "xhigh")
    if current == "high":
        current = "xhigh"
    if current not in order:
        return "low"
    index = order.index(current)
    return order[min(index + 1, len(order) - 1)]


def _describe_upstream_failure(exc: BaseException) -> str:
    """Human-readable failure; httpx timeouts often stringify to nothing useful."""
    if isinstance(exc, httpx.TimeoutException):
        return (
            "The model timed out mid-reply. Long documents can take more than "
            "a few minutes to write into write_file — for an uploaded Markdown "
            "file use convert_upload_to_docx instead, or try a shorter page "
            "count / send the request again."
        )
    detail = str(exc).strip()
    lowered = detail.lower()
    if "upstream 500" in lowered or "internal server error" in lowered:
        return (
            "The model server returned an internal error (500). It may have "
            "run out of memory or crashed mid-reply — reload the model in "
            "LM Studio (or restart it), then send “continue”."
        )
    return detail or f"{type(exc).__name__}: the model endpoint failed"


class AgentService:
    def __init__(
        self,
        upstream: UpstreamClient,
        tools: ToolRegistry,
        settings: Settings,
        skills: SkillCatalog,
        approvals: ApprovalBroker,
        memories: MemoryRepository,
        user_id: UUID,
        files: FileRepository | None = None,
    ) -> None:
        self._upstream = upstream
        self._tools = tools
        self._settings = settings
        self._skills = skills
        self._approvals = approvals
        self._memories = memories
        self._user_id = user_id
        self._files = files

    async def _system_prompt(
        self,
        *,
        web_search: bool = False,
        research: bool = False,
        skill: str | None = None,
    ) -> str:
        """Base prompt, today's date, user memory, and the skill index.

        Only skill names and descriptions go in — the bodies are pulled by the
        `read_skill` tool if and when the model decides one applies.
        """
        # Without this the model dates itself to its training cutoff, which makes
        # it treat stale recall as current and decline time-sensitive questions.
        today = datetime.now().astimezone()
        prompt = (
            f"{self._settings.system_prompt}\n\n"
            f"Today's date is {today:%A, %d %B %Y}. Anything you remember as "
            "'current' may be years out of date; check rather than assume."
        )

        about = await self._memories.prompt_block(self._user_id)
        if about:
            prompt = f"{prompt}\n\n{about}"

        prefs: list[str] = []
        if web_search:
            prefs.append(
                "Web search is ON for this turn. Use `web_search` (and "
                "`fetch_url` when needed) for facts, news, docs, or anything "
                "that may have changed since your training data."
            )
        else:
            prefs.append(
                "Web search is OFF for this turn. Do not call `web_search` "
                "unless the user explicitly asks you to search the web."
            )
        if research:
            prefs.append(
                "Research mode is ON. Prefer loading the `research` skill with "
                "`read_skill`, then investigate thoroughly before answering."
            )
        if skill:
            prefs.append(
                f"The user selected the skill `{skill}` (slash command). "
                "Its full instructions are already loaded in this turn — "
                "follow them for the reply. Do not call `read_skill` again "
                f"for {skill!r} unless you need a different skill."
            )
        prompt = (
            f"{prompt}\n\n## Session tools\n\n"
            + "\n".join(f"- {line}" for line in prefs)
        )

        index = self._skills.index()
        if not index:
            return prompt
        return (
            f"{prompt}\n\n"
            "## Available skills\n\n"
            "Each line is a skill you can load. When a skill's description matches "
            "the user's request, call `read_skill` with its name BEFORE answering, "
            "then follow the instructions it returns.\n\n"
            f"{index}"
        )

    async def run(
        self,
        messages: list[dict[str, Any]],
        model: str | None = None,
        effort: str | None = None,
        conversation_id: str | None = None,
        auto_approve_tools: set[str] | None = None,
        web_search: bool = False,
        research: bool = False,
        skill: str | None = None,
    ) -> AsyncIterator[AgentEvent]:
        """Drive the loop, emitting typed events the UI renders by type.

        `effort` is passed through to the endpoint, which shortens the model's
        thinking. It also caps the loop: at minimal effort the point is a fast
        answer, so a long tool chain would defeat it.
        """
        conversation: list[dict[str, Any]] = [
            {
                "role": "system",
                "content": await self._system_prompt(
                    web_search=web_search,
                    research=research,
                    skill=skill,
                ),
            },
            *messages,
        ]
        # Slash skill must load even when the model skips tools — same
        # reliability as the old "Use the skill … Call read_skill" prompt.
        if skill:
            async for event in self._inject_selected_skill(skill, conversation):
                yield event
        skip_approval = {
            name
            for name in (auto_approve_tools or set())
            if name in self._settings.approval_required_tools
        }
        soak = SoakTracker(
            conversation_id=conversation_id,
            user_id=str(self._user_id) if self._user_id else None,
        )

        try:
            chosen = model or await self._upstream.resolve_model()
        except (httpx.HTTPError, UpstreamError, KeyError) as exc:
            yield ErrorEvent(message=f"Cannot reach {self._settings.upstream} — {exc}")
            return

        max_steps = self._step_budget(effort)
        steps_used = 0
        empty_retries = 0
        # May drop on empty-reply recovery — high reasoning often burns the
        # whole token budget and never emits a tool call.
        active_effort = effort
        logger.info(
            "chat start model=%s effort=%s max_steps=%s conversation=%s",
            chosen,
            effort or "default",
            max_steps,
            conversation_id or "-",
        )

        # Ceiling is on charged tool rounds; setup tools (list/search/skills)
        # get extra iterations so exploration does not block write_file.
        for round_index in range(max_steps + _SETUP_ALLOWANCE):
            if steps_used >= max_steps:
                break

            assistant_message: dict[str, Any] | None = None
            streamed_text: list[str] = []
            saw_reasoning = False
            cut_runaway = False
            logger.info(
                "model call #%s model=%s tools=%s effort=%s",
                round_index + 1,
                chosen,
                len(self._tools.schemas),
                active_effort or "default",
            )
            try:
                chunks = self._upstream.stream_completion(
                    model=chosen,
                    messages=conversation,
                    tools=self._tools.schemas,
                    known_tool_names=self._tools.names,
                    effort=active_effort,
                    max_tokens=self._completion_budget(active_effort),
                )
                async for chunk in chunks:
                    if chunk.text is not None:
                        streamed_text.append(chunk.text)
                        joined = "".join(streamed_text)
                        if is_runaway_repetition(joined):
                            # Stop feeding the UI more spam; keep a short laugh.
                            cut_runaway = True
                            cleaned = trim_runaway_tail(joined)
                            # Only the excess beyond what we already showed.
                            already = len(joined) - len(chunk.text)
                            if len(cleaned) > already:
                                yield TextDeltaEvent(text=cleaned[already:])
                            assistant_message = {
                                "role": "assistant",
                                "content": cleaned,
                            }
                            break
                        yield TextDeltaEvent(text=chunk.text)
                    elif chunk.reasoning is not None:
                        saw_reasoning = True
                        yield ReasoningDeltaEvent(text=chunk.reasoning)
                    elif chunk.tool_progress is not None:
                        yield ToolCallDeltaEvent(**chunk.tool_progress)
                    else:
                        assistant_message = chunk.message
                        if cut_runaway:
                            break
            except (httpx.HTTPError, UpstreamError) as exc:
                logger.warning("model call failed model=%s: %s", chosen, exc)
                yield ErrorEvent(message=_describe_upstream_failure(exc))
                return

            if assistant_message is None:
                yield ErrorEvent(message="Upstream closed the stream without a reply.")
                return

            if cut_runaway:
                conversation.append(assistant_message)
                logger.info("chat done model=%s reason=runaway_cutoff", chosen)
                yield DoneEvent(steps=steps_used + 1)
                return

            conversation.append(assistant_message)
            tool_calls = assistant_message.get("tool_calls")
            if not tool_calls:
                # A reply with neither text nor tool calls is a failure wearing
                # a success's clothes; saying so beats rendering a blank turn.
                content = (assistant_message.get("content") or "").strip()
                if not content:
                    # Common with high reasoning_effort: thinking burns
                    # max_tokens and the stream ends with no tool call.
                    if empty_retries < 2:
                        empty_retries += 1
                        prev = active_effort
                        active_effort = _downgrade_effort(active_effort)
                        logger.warning(
                            "empty reply model=%s reasoning=%s; "
                            "retry %s effort %s→%s",
                            chosen,
                            saw_reasoning,
                            empty_retries,
                            prev or "default",
                            active_effort or "default",
                        )
                        # Drop the blank assistant turn — models handle a
                        # retry nudge better without a null-content message.
                        conversation.pop()
                        conversation.append(
                            {
                                "role": "user",
                                "content": (
                                    "Your last reply was empty (no text and no "
                                    "tool call). Continue the task now: call "
                                    "the tools you need (usually run_python or "
                                    "write_file). Keep reasoning short and put "
                                    "the full action in the tool call."
                                ),
                            }
                        )
                        continue
                    logger.warning(
                        "empty reply model=%s steps=%s reasoning=%s",
                        chosen,
                        steps_used,
                        saw_reasoning,
                    )
                    hint = (
                        " It spent the token budget on thinking and never "
                        "emitted a tool call."
                        if saw_reasoning
                        else ""
                    )
                    yield ErrorEvent(
                        message=(
                            f"{chosen} returned an empty reply.{hint} "
                            "Switch Effort to medium (or low), reload the model "
                            "in LM Studio if needed, then send “continue”."
                        )
                    )
                    return
                logger.info(
                    "chat done model=%s steps=%s reply=%s",
                    chosen,
                    steps_used,
                    _preview(content),
                )
                yield DoneEvent(steps=steps_used + 1)
                return

            for call in tool_calls:
                call_id, function = call["id"], call["function"]
                name, raw_arguments = function["name"], function["arguments"]
                logger.info(
                    "tool call model=%s name=%s args=%s",
                    chosen,
                    name,
                    _preview(raw_arguments, 200),
                )
                if name == "edit_docx":
                    soak.edit_proposed(raw_arguments)
                else:
                    soak.tool_used(name, raw_arguments)

                yield ToolCallEvent(id=call_id, name=name, arguments=raw_arguments)

                # Incomplete gated calls: never ask Allow/Deny for a no-op.
                # Empty run_python args previously paused HITL, then still failed
                # with "missing code" and often provoked an LM Studio 500 next.
                if name in self._settings.approval_required_tools:
                    if arg_error := self._tools.argument_error(name, raw_arguments):
                        logger.info(
                            "tool incomplete-args name=%s preview=%s",
                            name,
                            _preview(arg_error),
                        )
                        if name == "edit_docx":
                            soak.edit_result(raw_arguments, arg_error)
                        yield ToolResultEvent(
                            id=call_id, name=name, result=arg_error
                        )
                        conversation.append(
                            build_tool_message(call_id, name, arg_error)
                        )
                        continue

                if (
                    conversation_id
                    and name in self._settings.approval_required_tools
                    and name not in skip_approval
                ):
                    approval_card = None
                    approval_payload = None
                    if name == "edit_docx" and self._files is not None:
                        (
                            approval_payload,
                            approval_card,
                            prep_error,
                        ) = await prepare_edit_docx_approval(
                            self._files, self._user_id, raw_arguments
                        )
                        if prep_error:
                            soak.edit_result(raw_arguments, prep_error)
                            yield ToolResultEvent(
                                id=call_id, name=name, result=prep_error
                            )
                            conversation.append(
                                build_tool_message(call_id, name, prep_error)
                            )
                            continue

                    yield ToolApprovalEvent(
                        id=call_id,
                        name=name,
                        arguments=raw_arguments,
                        approval_card=approval_card,
                    )
                    allowed = await self._approvals.wait(
                        conversation_id,
                        call_id,
                        timeout=self._settings.approval_timeout,
                        payload=approval_payload,
                    )
                    if not allowed:
                        result = (
                            "Error: the user declined this action. "
                            "Do not retry the same write unless they ask."
                        )
                        logger.info("tool denied name=%s", name)
                        if name == "edit_docx":
                            soak.edit_denied(raw_arguments)
                        yield ToolResultEvent(id=call_id, name=name, result=result)
                        conversation.append(
                            build_tool_message(call_id, name, result)
                        )
                        continue

                    if name == "edit_docx" and self._files is not None:
                        taken = self._approvals.take_payload(
                            conversation_id, call_id
                        )
                        if taken is None:
                            result = (
                                "Error: approval payload missing, expired, or "
                                "already applied; nothing written. Re-read and "
                                "propose the edit again."
                            )
                        else:
                            result = await apply_edit_docx_payload(
                                self._files, self._user_id, taken
                            )
                        soak.edit_result(raw_arguments, result)
                        logger.info(
                            "tool result name=%s chars=%s preview=%s",
                            name,
                            len(result or ""),
                            _preview(result),
                        )
                        yield ToolResultEvent(id=call_id, name=name, result=result)
                        conversation.append(
                            build_tool_message(call_id, name, result)
                        )
                        continue
                elif name in skip_approval:
                    logger.info("tool auto-approved name=%s", name)

                result = await self._tools.invoke(name, raw_arguments)
                if name == "edit_docx":
                    soak.edit_result(raw_arguments, result)
                logger.info(
                    "tool result name=%s chars=%s preview=%s",
                    name,
                    len(result or ""),
                    _preview(result),
                )
                yield ToolResultEvent(id=call_id, name=name, result=result)

                conversation.append(build_tool_message(call_id, name, result))

            # Exploration (skills / list / search) is free. Heavy work
            # (read windows, python, write_file, web, …) spends the budget.
            if any(
                call["function"]["name"] not in _SETUP_TOOLS for call in tool_calls
            ):
                steps_used += 1

        async for event in self._wrap_up(conversation, chosen, effort, max_steps):
            yield event

    async def _inject_selected_skill(
        self,
        skill: str,
        conversation: list[dict[str, Any]],
    ) -> AsyncIterator[AgentEvent]:
        """Pre-load a slash-selected skill into the transcript and UI stream."""
        call_id = f"skill_{uuid4().hex[:24]}"
        arguments = json.dumps({"name": skill}, ensure_ascii=False)
        yield ToolCallEvent(id=call_id, name="read_skill", arguments=arguments)
        conversation.append(
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": call_id,
                        "type": "function",
                        "function": {
                            "name": "read_skill",
                            "arguments": arguments,
                        },
                    }
                ],
            }
        )
        try:
            body = self._skills.read(skill, max_chars=self._settings.max_skill_chars)
        except UnknownSkillError as exc:
            body = str(exc)
        yield ToolResultEvent(id=call_id, name="read_skill", result=body)
        conversation.append(build_tool_message(call_id, "read_skill", body))

    async def _wrap_up(
        self,
        conversation: list[dict[str, Any]],
        model: str,
        effort: str | None,
        max_steps: int,
    ) -> AsyncIterator[AgentEvent]:
        """Answer with what the tools already returned, budget spent.

        Ending on 'Stopped after N tool steps' threw away real work: the run
        that prompted this had already written the user's document and then
        reported nothing but the error. One more call, without tools, turns
        that into the answer the work had earned.
        """
        # Must be `user`, not `system`: Qwen (and many chat templates) reject
        # a system message anywhere after the first turn with a 500.
        conversation.append(
            {
                "role": "user",
                "content": (
                    "The tool budget for this turn is spent. Answer now using "
                    "only what the tool results above already gave you. If you "
                    "still need to create or update a file, say clearly that "
                    "you ran out of steps and ask the user to say \"continue\" "
                    "so you can call write_file next — do not pretend the file "
                    "was written. Be warm and conversational. If a file was "
                    "already written, say it is ready in one short sentence and "
                    "offer one next step — do not paste raw /api/files download "
                    "URLs (the UI already shows a download card)."
                ),
            }
        )

        logger.info("wrap-up call model=%s (tool budget spent)", model)
        answered = False
        try:
            chunks = self._upstream.stream_completion(
                model=model,
                messages=conversation,
                tools=[],
                known_tool_names=set(),
                effort=effort,
                max_tokens=self._completion_budget(effort),
            )
            async for chunk in chunks:
                if chunk.text is not None:
                    answered = True
                    yield TextDeltaEvent(text=chunk.text)
                elif chunk.reasoning is not None:
                    yield ReasoningDeltaEvent(text=chunk.reasoning)
        except (httpx.HTTPError, UpstreamError) as exc:
            logger.warning("wrap-up failed model=%s: %s", model, exc)
            yield ErrorEvent(message=_describe_upstream_failure(exc))
            return

        if not answered:
            yield ErrorEvent(
                message=(
                    f"Stopped after {max_steps} tool steps without finishing. "
                    "Send a follow-up like “continue and write the file”."
                )
            )
            return
        logger.info("chat done model=%s steps=%s reason=wrap_up", model, max_steps)
        yield DoneEvent(steps=max_steps)

    def _completion_budget(self, effort: str | None) -> int:
        """Token cap for one completion; high effort needs room for tools.

        With reasoning_effort=high, thinking can consume the whole budget and
        the stream ends with an empty reply (no text, no tool_calls). Give
        high/medium more headroom so run_python / write_file still fit.
        """
        base = self._settings.max_completion_tokens
        return {
            "minimal": min(base, 4_096),
            "low": min(base, 6_144),
            "medium": max(base, 8_192),
            "xhigh": max(base, 16_384),
            "high": max(base, 16_384),  # legacy alias
        }.get(effort or "", base)

    def _step_budget(self, effort: str | None) -> int:
        """How many charged tool rounds this effort level is allowed.

        Exploration tools do not spend this budget. xhigh uses the full
        `max_steps` ceiling so long document edits can finish on their own.
        """
        ceiling = self._settings.max_steps
        return min(
            ceiling,
            {
                "minimal": 4,
                "low": 8,
                "medium": 16,
                "xhigh": ceiling,
                "high": ceiling,  # legacy alias
            }.get(effort or "", ceiling),
        )
