"""Structured soak metrics for DOCX editing (Phase 1 close-out).

Logs go to logger ``agent_console.docx_soak`` as one JSON object per event.
Filter or ship these lines to measure real-world edit_docx behavior:

- operations proposed / applied
- validation / apply error types
- retries after an error in the same turn
- denied approvals
- fallbacks to ``run_python`` / ``write_file`` / ``convert_upload_to_docx``
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

__all__ = [
    "SoakTracker",
    "classify_edit_error",
    "ops_summary",
    "soak_log",
]

logger = logging.getLogger("agent_console.docx_soak")

_FALLBACK_TOOLS = frozenset(
    {"run_python", "write_file", "convert_upload_to_docx"}
)

_ERROR_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("generation_mismatch", re.compile(r"generation|re-read the document", re.I)),
    ("stale_hash", re.compile(r"stale|hash", re.I)),
    ("ambiguous_old", re.compile(r"ambiguous|more than one match", re.I)),
    ("old_not_found", re.compile(r"not found|no match", re.I)),
    ("multi_run_span", re.compile(r"multi_run_span", re.I)),
    ("field_or_revision", re.compile(r"\bins\b|\bdel\b|fldChar|fldSimple|revision|field", re.I)),
    ("denied", re.compile(r"user declined", re.I)),
    ("validation", re.compile(r"^Error:", re.I)),
)


def classify_edit_error(result: str | None) -> str | None:
    if not result:
        return None
    text = str(result)
    if not text.startswith("Error:") and "multi_run_span" not in text:
        return None
    for name, pattern in _ERROR_PATTERNS:
        if pattern.search(text):
            return name
    return "other"


def ops_summary(raw_arguments: str | dict[str, Any] | None) -> dict[str, Any]:
    """Compact, content-light summary of edit_docx arguments (no document text)."""
    args: dict[str, Any]
    if isinstance(raw_arguments, dict):
        args = raw_arguments
    else:
        try:
            args = json.loads(raw_arguments or "{}")
        except (TypeError, json.JSONDecodeError):
            return {"parse_error": True}
    ops = args.get("operations") if isinstance(args, dict) else None
    kinds: list[str] = []
    if isinstance(ops, list):
        for item in ops:
            if isinstance(item, dict):
                kinds.append(str(item.get("op") or "?"))
    return {
        "name": str(args.get("name") or "")[:120] if isinstance(args, dict) else "",
        "generation": args.get("generation") if isinstance(args, dict) else None,
        "op_count": len(kinds),
        "ops": kinds,
    }


def soak_log(event: str, **fields: Any) -> None:
    payload = {"event": event, **{k: v for k, v in fields.items() if v is not None}}
    logger.info("%s", json.dumps(payload, ensure_ascii=False, default=str))


class SoakTracker:
    """Per-agent-run tracker for retries and post-error fallbacks."""

    def __init__(self, conversation_id: str | None, user_id: str | None = None) -> None:
        self.conversation_id = conversation_id
        self.user_id = user_id
        self._edit_errors = 0
        self._last_edit_error: str | None = None

    def _base(self) -> dict[str, Any]:
        return {
            "conversation_id": self.conversation_id,
            "user_id": self.user_id,
        }

    def edit_proposed(self, raw_arguments: str) -> None:
        soak_log(
            "edit_docx_proposed",
            **self._base(),
            **ops_summary(raw_arguments),
        )

    def edit_result(self, raw_arguments: str, result: str) -> None:
        err = classify_edit_error(result)
        summary = ops_summary(raw_arguments)
        if err:
            self._edit_errors += 1
            self._last_edit_error = err
            soak_log(
                "edit_docx_error",
                **self._base(),
                **summary,
                error_type=err,
                retry_index=self._edit_errors,
                result_preview=(result or "")[:240],
            )
        else:
            soak_log(
                "edit_docx_applied",
                **self._base(),
                **summary,
                prior_errors=self._edit_errors,
                result_preview=(result or "")[:240],
            )
            self._edit_errors = 0
            self._last_edit_error = None

    def edit_denied(self, raw_arguments: str) -> None:
        soak_log(
            "edit_docx_denied",
            **self._base(),
            **ops_summary(raw_arguments),
        )
        self._edit_errors += 1
        self._last_edit_error = "denied"

    def tool_used(self, name: str, raw_arguments: str = "") -> None:
        if name not in _FALLBACK_TOOLS:
            return
        soak_log(
            "docx_path_tool",
            **self._base(),
            tool=name,
            after_edit_error=self._last_edit_error,
            edit_errors_in_turn=self._edit_errors,
            args_preview=(raw_arguments or "")[:160],
            likely_fallback=bool(self._last_edit_error),
        )
