"""Client for the self-hosted OpenAI-compatible endpoint."""

from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

import httpx

from agent_console.clients.streaming import (
    StreamFailed,
    ToolCallAccumulator,
    parse_sse_line,
    salvage_text_call,
)
from agent_console.config import Settings
from agent_console.models.chat import ToolCall, ToolSchema

__all__ = ["CompletionChunk", "UpstreamClient", "UpstreamError"]


class UpstreamError(RuntimeError):
    """The endpoint was reachable but did not answer usefully."""


@dataclass(slots=True)
class CompletionChunk:
    """One unit of progress from a streamed completion.

    Exactly one field is set. `text` and `reasoning` deltas arrive as they
    stream; `tool_progress` while a tool call's arguments are still growing;
    the assembled assistant message is emitted once at the end. Reasoning is
    carried separately because it must not enter the transcript.
    """

    text: str | None = None
    reasoning: str | None = None
    tool_progress: dict[str, Any] | None = None
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

    async def describe_image(
        self, data_url: str, question: str, model: str, timeout: float
    ) -> str:
        """Ask a multimodal model about one image and return its answer.

        Deliberately a plain request rather than part of the agent loop: the
        image never enters the main conversation, so the reasoning model — which
        cannot see — is never handed content it would fail on.
        """
        body = {
            "model": model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": question},
                        {"type": "image_url", "image_url": {"url": data_url}},
                    ],
                }
            ],
            "temperature": 0.2,
        }
        response = await self._http.post(
            f"{self._settings.upstream}/chat/completions", json=body, timeout=timeout
        )
        if response.status_code >= 400:
            raise UpstreamError(
                f"the vision model {model} rejected the image "
                f"({response.status_code}): {response.text[:200]}"
            )

        message = response.json()["choices"][0]["message"]
        answer = (message.get("content") or "").strip()
        if not answer:
            raise UpstreamError(f"{model} returned no description")
        return answer

    async def list_models(self) -> list[str]:
        """Every model the endpoint reports, for the picker."""
        response = await self._http.get(
            f"{self._settings.upstream}/models",
            timeout=self._settings.model_listing_timeout,
        )
        response.raise_for_status()
        return [entry["id"] for entry in response.json().get("data") or []]

    async def complete_text(
        self,
        model: str,
        messages: list[dict[str, Any]],
        *,
        temperature: float = 0.2,
        max_tokens: int = 1_200,
    ) -> str:
        """One non-streaming completion; used for context summarization."""
        body = {
            "model": model,
            "messages": messages,
            "stream": False,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        response = await self._http.post(
            f"{self._settings.upstream}/chat/completions",
            json=body,
            timeout=httpx.Timeout(120.0, connect=self._settings.connect_timeout),
        )
        if response.status_code >= 400:
            raise UpstreamError(
                f"upstream {response.status_code}: {response.text[:400]}"
            )
        message = response.json()["choices"][0]["message"]
        text = (message.get("content") or "").strip()
        if not text:
            raise UpstreamError(f"{model} returned an empty summary")
        return text

    async def stream_completion(
        self,
        model: str,
        messages: list[dict[str, Any]],
        tools: list[ToolSchema],
        known_tool_names: set[str],
        effort: str | None = None,
    ) -> AsyncIterator[CompletionChunk]:
        """Stream one completion, yielding text deltas then the final message."""
        body: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "stream": True,
            "temperature": 0.7,
        }
        # Omitted rather than sent empty: an empty `tools` array alongside
        # `tool_choice: auto` is rejected by some endpoints, and callers pass no
        # tools precisely when they want prose and nothing else.
        if tools:
            body["tools"] = [tool.model_dump() for tool in tools]
            body["tool_choice"] = "auto"
        # Measured against this endpoint: "minimal" cuts reasoning length by
        # roughly two thirds, which on a fixed token budget is the difference
        # between getting an answer and spending it all on thinking.
        if effort:
            body["reasoning_effort"] = effort
        body["max_tokens"] = self._settings.max_completion_tokens
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
                try:
                    delta = parse_sse_line(line)
                except StreamFailed as exc:
                    raise UpstreamError(
                        f"{model} failed mid-response: {exc}"
                    ) from exc
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
                for progress in accumulator.add(delta.get("tool_calls")):
                    yield CompletionChunk(tool_progress=progress)

        full_text = "".join(text_parts)
        tool_calls: list[ToolCall] = accumulator.result() or salvage_text_call(
            full_text, known_tool_names
        )

        message: dict[str, Any] = {"role": "assistant", "content": full_text or None}
        if tool_calls:
            message["tool_calls"] = [call.model_dump() for call in tool_calls]
        yield CompletionChunk(message=message)
