"""Ask the user a clarifying question with clickable options in the UI."""

from __future__ import annotations

import json

from agent_console.services.tools.context import ToolContext
from agent_console.services.tools.registry import ToolRegistry

__all__ = ["register"]

_MAX_OPTIONS = 8
_MAX_OPTION_CHARS = 120


def register(registry: ToolRegistry, context: ToolContext) -> None:
    del context  # no server state — the UI renders options from the tool call

    @registry.tool(
        name="ask_user",
        description=(
            "Ask the user a clarifying question with short clickable choices "
            "(which file, which theme/colors, what to change). Call this when "
            "the request is ambiguous, then STOP — do not call more tools until "
            "they reply. Prefer this over a long plain-text list."
        ),
        parameters={
            "type": "object",
            "properties": {
                "question": {
                    "type": "string",
                    "description": "One short question shown above the choices.",
                },
                "options": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": (
                        "2–8 short labels the user can tap (file names, theme "
                        "names, colors, or next-step choices)."
                    ),
                },
            },
            "required": ["question", "options"],
        },
    )
    async def ask_user(question: str = "", options: list[str] | None = None) -> str:
        q = (question or "").strip()
        raw = options if isinstance(options, list) else []
        cleaned: list[str] = []
        seen: set[str] = set()
        for item in raw:
            label = " ".join(str(item).split())
            if not label:
                continue
            if len(label) > _MAX_OPTION_CHARS:
                label = label[: _MAX_OPTION_CHARS - 1] + "…"
            key = label.casefold()
            if key in seen:
                continue
            seen.add(key)
            cleaned.append(label)
            if len(cleaned) >= _MAX_OPTIONS:
                break

        if not q:
            return "Error: missing `question`."
        if len(cleaned) < 2:
            return (
                "Error: pass at least 2 short `options` (e.g. file names or "
                "theme choices)."
            )

        # Structured echo so the UI can re-parse if args were clipped; the
        # model is told to wait for the next user message.
        payload = json.dumps(
            {"question": q, "options": cleaned}, ensure_ascii=False
        )
        return (
            "Shown clickable choices to the user. Do not call more tools. "
            "Wait for their next message picking an option (or typing freely). "
            f"Payload: {payload}"
        )
