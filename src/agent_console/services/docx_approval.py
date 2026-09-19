"""Server-built approval card for edit_docx (plain JSON for the Composer).

The UI only renders this structure — no diff logic in React — so the preview
matches what apply will do. Document text is always plain strings (never HTML).
"""

from __future__ import annotations

import difflib
import re
from typing import Any

from agent_console.services.docx_edit import BlockDiff, EditOp

__all__ = [
    "MAX_CARD_CHANGES",
    "build_approval_card",
    "truncate_around_change",
    "word_diff_segments",
]

MAX_CARD_CHANGES = 12
_CONTEXT_CHARS = 80
_MAX_SNIPPET = 240

_WORD_RE = re.compile(r"\S+|\s+")


def word_diff_segments(before: str, after: str) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    """Word-level diff segments for replace highlighting.

    Each segment is ``{"kind": "equal"|"delete"|"insert", "text": "..."}``.
    """
    before_parts = _WORD_RE.findall(before) or [before]
    after_parts = _WORD_RE.findall(after) or [after]
    matcher = difflib.SequenceMatcher(a=before_parts, b=after_parts, autojunk=False)
    before_segs: list[dict[str, str]] = []
    after_segs: list[dict[str, str]] = []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            text = "".join(before_parts[i1:i2])
            before_segs.append({"kind": "equal", "text": text})
            after_segs.append({"kind": "equal", "text": text})
        elif tag == "delete":
            before_segs.append({"kind": "delete", "text": "".join(before_parts[i1:i2])})
        elif tag == "insert":
            after_segs.append({"kind": "insert", "text": "".join(after_parts[j1:j2])})
        elif tag == "replace":
            before_segs.append({"kind": "delete", "text": "".join(before_parts[i1:i2])})
            after_segs.append({"kind": "insert", "text": "".join(after_parts[j1:j2])})
    return before_segs, after_segs


def truncate_around_change(before: str, after: str) -> tuple[str, str]:
    """Clip long paragraphs around the first differing region."""
    if len(before) <= _MAX_SNIPPET and len(after) <= _MAX_SNIPPET:
        return before, after
    matcher = difflib.SequenceMatcher(a=before, b=after, autojunk=False)
    start = 0
    end_b = len(before)
    end_a = len(after)
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag != "equal":
            start = max(0, min(i1, j1) - _CONTEXT_CHARS)
            end_b = min(len(before), i2 + _CONTEXT_CHARS)
            end_a = min(len(after), j2 + _CONTEXT_CHARS)
            break
    left = "…" if start > 0 else ""
    right_b = "…" if end_b < len(before) else ""
    right_a = "…" if end_a < len(after) else ""
    return (
        f"{left}{before[start:end_b]}{right_b}",
        f"{left}{after[start:end_a]}{right_a}",
    )


def build_approval_card(
    *,
    file_name: str,
    from_version: int,
    diffs: list[BlockDiff],
    ops: list[EditOp],
    notes: list[str] | None = None,
    max_changes: int = MAX_CARD_CHANGES,
) -> dict[str, Any]:
    """JSON-serializable card payload for ToolApprovalEvent / Composer."""
    changes: list[dict[str, Any]] = []
    for index, diff in enumerate(diffs[:max_changes]):
        op = ops[index] if index < len(ops) else None
        op_name = op.op if op else "edit"
        before_t, after_t = truncate_around_change(diff.before, diff.after)
        entry: dict[str, Any] = {
            "op": op_name,
            "block_id": diff.block_id,
            "before": before_t,
            "after": after_t,
            "notes": [],
        }
        if op_name == "replace":
            before_segs, after_segs = word_diff_segments(before_t, after_t)
            entry["before_segments"] = before_segs
            entry["after_segments"] = after_segs
        changes.append(entry)

    omitted = max(0, len(diffs) - len(changes))
    card_notes = list(notes or [])
    return {
        "file_name": file_name,
        "from_version": from_version,
        "to_version": from_version + 1,
        "change_count": len(diffs),
        "changes": changes,
        "omitted_count": omitted,
        "notes": card_notes,
    }
