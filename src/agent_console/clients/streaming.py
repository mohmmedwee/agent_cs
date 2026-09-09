"""Reassembly of Server-Sent Event streams from an OpenAI-compatible endpoint.

A single tool call arrives across several chunks — the name split mid-word, the
JSON arguments a few characters at a time — keyed by `index`. Fragments must be
concatenated per index; overwriting instead of appending is the classic bug, and
it only shows up once arguments are long enough to span chunks.

This module is deliberately free of I/O so both the async server path and the
synchronous diagnostic script can share one implementation.
"""

import json
import re
from typing import Any

from agent_console.models.chat import FunctionCall, ToolCall

__all__ = [
    "SSE_DATA_PREFIX",
    "StreamFailed",
    "ToolCallAccumulator",
    "parse_sse_line",
    "salvage_text_call",
]

SSE_DATA_PREFIX = "data: "
_DONE_SENTINEL = "[DONE]"


class StreamFailed(RuntimeError):
    """The endpoint reported a failure inside an otherwise-200 stream."""


def parse_sse_line(line: str) -> dict[str, Any] | None:
    """Decode one `data:` line into a delta dict.

    Returns None for keep-alives, non-data lines, the [DONE] sentinel, and
    malformed JSON — all of which callers should simply skip.

    Raises StreamFailed when the frame carries an error. The endpoint answers
    200 and only then streams `event: error`, so a failure looks exactly like a
    successful empty completion unless it is checked for here — which is how a
    dead model turned into a blank reply rather than a visible problem.
    """
    if not line.startswith(SSE_DATA_PREFIX):
        return None
    payload = line[len(SSE_DATA_PREFIX) :].strip()
    if payload == _DONE_SENTINEL:
        return None

    try:
        body = json.loads(payload)
    except json.JSONDecodeError:
        return None

    if isinstance(body, dict) and (problem := body.get("error")):
        detail = problem.get("message") if isinstance(problem, dict) else problem
        raise StreamFailed(str(detail)[:400])

    try:
        return body["choices"][0].get("delta") or {}
    except (KeyError, IndexError, TypeError):
        return None


class ToolCallAccumulator:
    """Concatenates streamed tool-call fragments into complete calls."""

    # Emit a progress tick at least this often so a silent multi-page write
    # still shows the byte count climbing, without one SSE frame per token.
    _PROGRESS_EVERY = 256

    def __init__(self) -> None:
        self._slots: dict[int, ToolCall] = {}
        self._emitted_chars: dict[int, int] = {}

    def add(self, deltas: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
        """Fold one delta's `tool_calls` array; return progress for the UI.

        Each returned dict is safe to forward as-is: name and size only, never
        the argument body. Callers that only want the final calls can ignore it.
        """
        progress: list[dict[str, Any]] = []
        for fragment in deltas or []:
            index = int(fragment.get("index", 0))
            slot = self._slots.setdefault(index, ToolCall())
            name_before = slot.function.name
            chars_before = len(slot.function.arguments)

            if call_id := fragment.get("id"):
                slot.id = call_id
            function = fragment.get("function") or {}
            if name := function.get("name"):
                slot.function.name += name
            if arguments := function.get("arguments"):
                slot.function.arguments += arguments

            chars = len(slot.function.arguments)
            last_emitted = self._emitted_chars.get(index, -self._PROGRESS_EVERY)
            name_changed = slot.function.name != name_before
            grew_enough = chars - last_emitted >= self._PROGRESS_EVERY
            first_sight = chars_before == 0 and (chars > 0 or bool(slot.function.name))
            if name_changed or grew_enough or first_sight or (
                fragment.get("id") and not chars_before
            ):
                self._emitted_chars[index] = chars
                progress.append(
                    {
                        "index": index,
                        "id": slot.id,
                        "name": slot.function.name,
                        "arguments_chars": chars,
                    }
                )
        return progress

    def result(self) -> list[ToolCall]:
        """Completed calls, ordered by their stream index."""
        return [self._slots[index] for index in sorted(self._slots)]

    def __bool__(self) -> bool:
        return bool(self._slots)


# Fallback for endpoints with no tool-call parser: the model prints the call as
# text instead of emitting a tool_calls array. Fix the serving config properly —
# this only keeps you moving in the meantime.
_JSON_CALL = re.compile(
    r'\{\s*"(?:name|tool|function)"\s*:\s*"([\w-]+)"\s*,\s*'
    r'"(?:arguments|parameters|args)"\s*:\s*(\{.*?\})\s*\}',
    re.S,
)


def salvage_text_call(text: str, known_tools: set[str]) -> list[ToolCall]:
    """Recover a tool call the model printed as prose. Empty list if there is none."""
    match = _JSON_CALL.search(text or "")
    if not match or match.group(1) not in known_tools:
        return []
    name, arguments = match.group(1), match.group(2)
    return [ToolCall(id=f"salvaged_{name}", function=FunctionCall(name=name, arguments=arguments))]
