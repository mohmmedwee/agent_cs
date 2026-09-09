"""Client for the self-hosted OpenAI-compatible endpoint."""

from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

import httpx

from agent_console.clients.streaming import ToolCallAccumulator, parse_sse_line, salvage_text_call
from agent_console.config import Settings
from agent_console.models.chat import ToolCall, ToolSchema

__all__ = ["CompletionChunk", "UpstreamClient", "UpstreamError"]


class UpstreamError(RuntimeError):
    """The endpoint was reachable but did not answer usefully."""


@dataclass(slots=True)
class CompletionChunk:
    """One unit of progress from a streamed completion.

    Exactly one field is set. `text` and `reasoning` deltas arrive as they
    stream; the assembled assistant message is emitted once at the end.
    Reasoning is carried separately because it must not enter the transcript.
    """

    text: str | None = None
    reasoning: str | None = None
    message: dict[str, Any] | None = None


class UpstreamClient:
    """Talks to the model endpoint. Owns no application logic."""

    def __init__(self, http: httpx.AsyncClient, settings: Settings) -> None:
        self._http = http
        self._settings = settings
        self._resolved_model: str | None = None

    async def resolve_model(self) -> str:
        """The configured model, or the first one the endpoint reports. Cached."""
        if self._settings.model:
            return self._settings.model
        if self._resolved_model:
            return self._resolved_model

        response = await self._http.get(
            f"{self._settings.upstream}/models",
            timeout=self._settings.model_listing_timeout,
        )
        response.raise_for_status()
        models = response.json().get("data") or []
        if not models:
            raise UpstreamError(f"{self._settings.upstream} reports no loaded models")
        self._resolved_model = models[0]["id"]
        return self._resolved_model

    async def stream_completion(
        self,
        model: str,
        messages: list[dict[str, Any]],
        tools: list[ToolSchema],
        known_tool_names: set[str],
    ) -> AsyncIterator[CompletionChunk]:
        """Stream one completion, yielding text deltas then the final message."""
        body = {
            "model": model,
            "messages": messages,
            "tools": [tool.model_dump() for tool in tools],
            "tool_choice": "auto",
            "stream": True,
            "temperature": 0.7,
        }
        text_parts: list[str] = []
        accumulator = ToolCallAccumulator()

        async with self._http.stream(
            "POST",
            f"{self._settings.upstream}/chat/completions",
            json=body,
            timeout=httpx.Timeout(
                self._settings.request_timeout, connect=self._settings.connect_timeout
            ),
        ) as response:
            if response.status_code >= 400:
                detail = (await response.aread()).decode()[:400]
                raise UpstreamError(f"upstream {response.status_code}: {detail}")

            async for line in response.aiter_lines():
                delta = parse_sse_line(line)
                if delta is None:
                    continue
                if chunk := delta.get("content"):
                    text_parts.append(chunk)
                    yield CompletionChunk(text=chunk)
                # Reasoning models emit their scratch work here first and can
                # think for minutes. Forward it so the caller can show progress,
                # but keep it out of `text_parts` — it is not part of the reply.
                if thought := delta.get("reasoning_content"):
                    yield CompletionChunk(reasoning=thought)
                accumulator.add(delta.get("tool_calls"))

        full_text = "".join(text_parts)
        tool_calls: list[ToolCall] = accumulator.result() or salvage_text_call(
            full_text, known_tool_names
        )

        message: dict[str, Any] = {"role": "assistant", "content": full_text or None}
        if tool_calls:
            message["tool_calls"] = [call.model_dump() for call in tool_calls]
        yield CompletionChunk(message=message)
