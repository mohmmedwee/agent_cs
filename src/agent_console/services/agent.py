"""The agent loop.

Call the model; if the reply carries tool calls, run them, append the results as
`role: tool` messages, and call again. Stop when a reply has no tool calls, or
after `max_steps` rounds.
"""

from collections.abc import AsyncIterator
from datetime import datetime
from typing import Any

import httpx

from uuid import UUID

from agent_console.clients.upstream import UpstreamClient, UpstreamError
from agent_console.config import Settings
from agent_console.models.chat import build_tool_message
from agent_console.repositories.memory import MemoryRepository
from agent_console.repositories.skills import SkillRepository
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

__all__ = ["AgentService"]

# Loading a skill costs a round trip but produces no progress, so it is not
# charged to the step budget. This bounds how many such rounds a model can take
# before the loop gives up on it ever doing anything else.
SKILL_TOOL = "read_skill"
_SKILL_ALLOWANCE = 3


def _describe_upstream_failure(exc: BaseException) -> str:
    """Human-readable failure; httpx timeouts often stringify to nothing useful."""
    if isinstance(exc, httpx.TimeoutException):
        return (
            "The model timed out mid-reply. Long documents can take more than "
            "a few minutes to write into write_file — try a shorter page count, "
            "or wait and send the request again."
        )
    detail = str(exc).strip()
    return detail or f"{type(exc).__name__}: the model endpoint failed"


class AgentService:
    def __init__(
        self,
        upstream: UpstreamClient,
        tools: ToolRegistry,
        settings: Settings,
        skills: SkillRepository,
        approvals: ApprovalBroker,
        memories: MemoryRepository,
        user_id: UUID,
    ) -> None:
        self._upstream = upstream
        self._tools = tools
        self._settings = settings
        self._skills = skills
        self._approvals = approvals
        self._memories = memories
        self._user_id = user_id

    async def _system_prompt(self) -> str:
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
    ) -> AsyncIterator[AgentEvent]:
        """Drive the loop, emitting typed events the UI renders by type.

        `effort` is passed through to the endpoint, which shortens the model's
        thinking. It also caps the loop: at minimal effort the point is a fast
        answer, so a long tool chain would defeat it.
        """
        conversation: list[dict[str, Any]] = [
            {"role": "system", "content": await self._system_prompt()},
            *messages,
        ]

        try:
            chosen = model or await self._upstream.resolve_model()
        except (httpx.HTTPError, UpstreamError, KeyError) as exc:
            yield ErrorEvent(message=f"Cannot reach {self._settings.upstream} — {exc}")
            return

        max_steps = self._step_budget(effort)
        steps_used = 0

        # The ceiling is on tool rounds, but the extra iterations let a model
        # load skills first without those reads eating the budget.
        for _ in range(max_steps + _SKILL_ALLOWANCE):
            if steps_used >= max_steps:
                break

            assistant_message: dict[str, Any] | None = None
            streamed_text: list[str] = []
            cut_runaway = False
            try:
                chunks = self._upstream.stream_completion(
                    model=chosen,
                    messages=conversation,
                    tools=self._tools.schemas,
                    known_tool_names=self._tools.names,
                    effort=effort,
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
                        yield ReasoningDeltaEvent(text=chunk.reasoning)
                    elif chunk.tool_progress is not None:
                        yield ToolCallDeltaEvent(**chunk.tool_progress)
                    else:
                        assistant_message = chunk.message
                        if cut_runaway:
                            break
            except (httpx.HTTPError, UpstreamError) as exc:
                yield ErrorEvent(message=_describe_upstream_failure(exc))
                return

            if assistant_message is None:
                yield ErrorEvent(message="Upstream closed the stream without a reply.")
                return

            if cut_runaway:
                conversation.append(assistant_message)
                yield DoneEvent(steps=steps_used + 1)
                return

            conversation.append(assistant_message)
            tool_calls = assistant_message.get("tool_calls")
            if not tool_calls:
                # A reply with neither text nor tool calls is a failure wearing
                # a success's clothes; saying so beats rendering a blank turn.
                if not (assistant_message.get("content") or "").strip():
                    yield ErrorEvent(
                        message=(
                            f"{chosen} returned an empty reply. The model may have "
                            "failed to run — try another model in Settings."
                        )
                    )
                    return
                yield DoneEvent(steps=steps_used + 1)
                return

            for call in tool_calls:
                call_id, function = call["id"], call["function"]
                name, raw_arguments = function["name"], function["arguments"]

                yield ToolCallEvent(id=call_id, name=name, arguments=raw_arguments)

                if (
                    conversation_id
                    and name in self._settings.approval_required_tools
                ):
                    yield ToolApprovalEvent(
                        id=call_id, name=name, arguments=raw_arguments
                    )
                    allowed = await self._approvals.wait(
                        conversation_id,
                        call_id,
                        timeout=self._settings.approval_timeout,
                    )
                    if not allowed:
                        result = (
                            "Error: the user declined this action. "
                            "Do not retry the same write unless they ask."
                        )
                        yield ToolResultEvent(id=call_id, name=name, result=result)
                        conversation.append(
                            build_tool_message(call_id, name, result)
                        )
                        continue

                result = await self._tools.invoke(name, raw_arguments)
                yield ToolResultEvent(id=call_id, name=name, result=result)

                conversation.append(build_tool_message(call_id, name, result))

            # Reading a skill is setup, not progress toward the answer. Charging
            # it to the budget spent half of a minimal-effort run on loading
            # instructions the model then had no room left to act on.
            if any(call["function"]["name"] != SKILL_TOOL for call in tool_calls):
                steps_used += 1

        async for event in self._wrap_up(conversation, chosen, effort, max_steps):
            yield event

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
                    "only what the tool results above already gave you. Be warm "
                    "and conversational — not a status report. If a file was "
                    "written, say it is ready in one short sentence and offer "
                    "one next step — do not paste raw /api/files download URLs "
                    "(the UI already shows a download card). If the task is "
                    "unfinished, say briefly what is left and that raising "
                    "Effort in Settings allows more steps."
                ),
            }
        )

        answered = False
        try:
            chunks = self._upstream.stream_completion(
                model=model,
                messages=conversation,
                tools=[],
                known_tool_names=set(),
                effort=effort,
            )
            async for chunk in chunks:
                if chunk.text is not None:
                    answered = True
                    yield TextDeltaEvent(text=chunk.text)
                elif chunk.reasoning is not None:
                    yield ReasoningDeltaEvent(text=chunk.reasoning)
        except (httpx.HTTPError, UpstreamError) as exc:
            yield ErrorEvent(message=_describe_upstream_failure(exc))
            return

        if not answered:
            yield ErrorEvent(
                message=(
                    f"Stopped after {max_steps} tool steps without an answer. "
                    "Raise Effort in Settings to allow more."
                )
            )
            return
        yield DoneEvent(steps=max_steps)

    def _step_budget(self, effort: str | None) -> int:
        """How many tool rounds this effort level is allowed.

        Backs the effort control with something that definitely works,
        independent of what the endpoint does with `reasoning_effort`.
        """
        ceiling = self._settings.max_steps
        return min(ceiling, {"minimal": 2, "low": 4, "medium": 8}.get(effort or "", ceiling))
