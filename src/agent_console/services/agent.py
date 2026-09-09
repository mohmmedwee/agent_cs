"""The agent loop.

Call the model; if the reply carries tool calls, run them, append the results as
`role: tool` messages, and call again. Stop when a reply has no tool calls, or
after `max_steps` rounds.
"""

from collections.abc import AsyncIterator
from datetime import datetime
from typing import Any

import httpx

from agent_console.clients.upstream import UpstreamClient, UpstreamError
from agent_console.config import Settings
from agent_console.models.chat import build_tool_message
from agent_console.repositories.skills import SkillRepository
from agent_console.models.events import (
    AgentEvent,
    DoneEvent,
    ErrorEvent,
    ReasoningDeltaEvent,
    TextDeltaEvent,
    ToolCallEvent,
    ToolResultEvent,
)
from agent_console.services.tools import ToolRegistry

__all__ = ["AgentService"]


class AgentService:
    def __init__(
        self,
        upstream: UpstreamClient,
        tools: ToolRegistry,
        settings: Settings,
        skills: SkillRepository,
    ) -> None:
        self._upstream = upstream
        self._tools = tools
        self._settings = settings
        self._skills = skills

    def _system_prompt(self) -> str:
        """Base prompt, today's date, and the skill index.

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

    async def run(self, messages: list[dict[str, Any]]) -> AsyncIterator[AgentEvent]:
        """Drive the loop, emitting typed events the UI renders by type."""
        conversation: list[dict[str, Any]] = [
            {"role": "system", "content": self._system_prompt()},
            *messages,
        ]

        try:
            model = await self._upstream.resolve_model()
        except (httpx.HTTPError, UpstreamError, KeyError) as exc:
            yield ErrorEvent(message=f"Cannot reach {self._settings.upstream} — {exc}")
            return

        for step in range(self._settings.max_steps):
            assistant_message: dict[str, Any] | None = None
            try:
                chunks = self._upstream.stream_completion(
                    model=model,
                    messages=conversation,
                    tools=self._tools.schemas,
                    known_tool_names=self._tools.names,
                )
                async for chunk in chunks:
                    if chunk.text is not None:
                        yield TextDeltaEvent(text=chunk.text)
                    elif chunk.reasoning is not None:
                        yield ReasoningDeltaEvent(text=chunk.reasoning)
                    else:
                        assistant_message = chunk.message
            except (httpx.HTTPError, UpstreamError) as exc:
                yield ErrorEvent(message=str(exc))
                return

            if assistant_message is None:
                yield ErrorEvent(message="Upstream closed the stream without a reply.")
                return

            conversation.append(assistant_message)
            tool_calls = assistant_message.get("tool_calls")
            if not tool_calls:
                yield DoneEvent(steps=step + 1)
                return

            for call in tool_calls:
                call_id, function = call["id"], call["function"]
                name, raw_arguments = function["name"], function["arguments"]

                yield ToolCallEvent(id=call_id, name=name, arguments=raw_arguments)
                result = await self._tools.invoke(name, raw_arguments)
                yield ToolResultEvent(id=call_id, name=name, result=result)

                conversation.append(build_tool_message(call_id, name, result))

        yield ErrorEvent(message=f"Stopped after {self._settings.max_steps} tool steps.")
