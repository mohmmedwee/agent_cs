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

__all__ = ["SSE_DATA_PREFIX", "ToolCallAccumulator", "parse_sse_line", "salvage_text_call"]

SSE_DATA_PREFIX = "data: "
_DONE_SENTINEL = "[DONE]"


def parse_sse_line(line: str) -> dict[str, Any] | None:
    """Decode one `data:` line into a delta dict.

    Returns None for keep-alives, non-data lines, the [DONE] sentinel, and
    malformed JSON — all of which callers should simply skip.
    """
    if not line.startswith(SSE_DATA_PREFIX):
        return None
    payload = line[len(SSE_DATA_PREFIX) :].strip()
    if payload == _DONE_SENTINEL:
        return None
    try:
        return json.loads(payload)["choices"][0].get("delta") or {}
    except (json.JSONDecodeError, KeyError, IndexError):
        return None


class ToolCallAccumulator:
    """Concatenates streamed tool-call fragments into complete calls."""

    def __init__(self) -> None:
        self._slots: dict[int, ToolCall] = {}

    def add(self, deltas: list[dict[str, Any]] | None) -> None:
        """Fold one delta's `tool_calls` array into the accumulated state."""
        for fragment in deltas or []:
            slot = self._slots.setdefault(fragment.get("index", 0), ToolCall())
            if call_id := fragment.get("id"):
                slot.id = call_id
            function = fragment.get("function") or {}
            if name := function.get("name"):
                slot.function.name += name
            if arguments := function.get("arguments"):
                slot.function.arguments += arguments

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
