"""Score edit_docx e2e transcripts (slice 7)."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from tests.edit_docx_e2e_corpus import E2ECase


@dataclass
class ScoreCard:
    case_id: str
    correct_tool_path: bool
    correct_result: bool
    formatting_preserved: bool
    no_forbidden_fallback: bool
    retries: int
    notes: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return (
            self.correct_tool_path
            and self.correct_result
            and self.formatting_preserved
            and self.no_forbidden_fallback
        )

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["passed"] = self.passed
        return d


def _tool_names(events: list[dict[str, Any]]) -> list[str]:
    names: list[str] = []
    for ev in events:
        if (ev.get("type") or ev.get("event")) == "tool_call":
            name = ev.get("name") or ev.get("tool")
            if name:
                names.append(str(name))
    return names


def _assistant_text(events: list[dict[str, Any]]) -> str:
    parts: list[str] = []
    for ev in events:
        kind = ev.get("type") or ev.get("event")
        if kind == "text_delta" and ev.get("text"):
            parts.append(str(ev["text"]))
        elif kind in ("ask_user", "tool_approval") and ev.get("question"):
            parts.append(str(ev["question"]))
    return "".join(parts)


def _count_retries(events: list[dict[str, Any]]) -> int:
    """Count edit_docx calls after an error result (simple heuristic)."""
    retries = 0
    saw_error = False
    for ev in events:
        kind = ev.get("type") or ev.get("event")
        if kind == "tool_result" and (ev.get("name") or "") == "edit_docx":
            result = str(ev.get("result") or "")
            if result.startswith("Error:") or "multi_run_span" in result:
                saw_error = True
            elif saw_error:
                retries += 1
                saw_error = False
        if kind == "tool_call" and (ev.get("name") or "") == "edit_docx" and saw_error:
            retries += 1
            saw_error = False
    return retries


def score_case(
    case: E2ECase,
    events: list[dict[str, Any]],
    tip_text: str | None,
) -> ScoreCard:
    tools = _tool_names(events)
    text = _assistant_text(events).lower()
    notes: list[str] = []

    # Tool path: required tools appeared (order flexible except ask-only cases).
    # Annotated search counts as the locate step in place of a full read.
    effective = list(tools)
    if "search_uploaded_files" in effective and "read_uploaded_file" not in effective:
        effective.append("read_uploaded_file")

    if case.expect_ask:
        correct_path = "ask_user" in tools or "ask" in text
        if not correct_path:
            notes.append("expected ask_user / clarification")
    else:
        missing = [t for t in case.expect_tools if t not in effective]
        correct_path = not missing
        if missing:
            notes.append(f"missing tools: {missing}")

    forbidden_hit = [t for t in case.forbid_tools if t in tools]
    # Footer case may legitimately use run_python — allow if listed in expect.
    if case.id == "footer_unsupported" and "run_python" in tools:
        forbidden_hit = [t for t in forbidden_hit if t != "run_python"]
    no_forbidden = not forbidden_hit
    if forbidden_hit:
        notes.append(f"forbidden tools: {forbidden_hit}")

    tip = tip_text or ""
    if case.expect_ask or case.expect_explain:
        correct_result = True
        if case.expect_ask and not (
            "ask_user" in tools or "?" in _assistant_text(events)
        ):
            correct_result = False
            notes.append("did not ask clarifying question")
        if case.expect_explain:
            explain_hints = (
                "tracked",
                "revision",
                "footer",
                "header",
                "cannot",
                "can't",
                "accept or reject",
                "run_python",
                "word first",
            )
            if not any(h in text for h in explain_hints):
                # still ok if edit_docx errored with field/revision wording
                err_ok = any(
                    "ins" in str(ev.get("result") or "").lower()
                    or "del" in str(ev.get("result") or "").lower()
                    or "revision" in str(ev.get("result") or "").lower()
                    or "footer" in str(ev.get("result") or "").lower()
                    for ev in events
                    if (ev.get("type") or "") == "tool_result"
                )
                if not err_ok:
                    correct_result = False
                    notes.append("missing user-facing explanation")
        formatting_ok = True
    else:
        missing_text = [s for s in case.expect_text if s not in tip]
        correct_result = not missing_text
        if missing_text:
            notes.append(f"tip missing: {missing_text}")
        lost = [s for s in case.preserve_text if s not in tip]
        formatting_ok = not lost
        if lost:
            notes.append(f"lost preserved text: {lost}")

    return ScoreCard(
        case_id=case.id,
        correct_tool_path=correct_path,
        correct_result=correct_result,
        formatting_preserved=formatting_ok,
        no_forbidden_fallback=no_forbidden,
        retries=_count_retries(events),
        notes=notes,
    )


def save_transcript(
    directory: Path,
    case_id: str,
    events: list[dict[str, Any]],
    score: ScoreCard,
    meta: dict[str, Any] | None = None,
) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{case_id}.json"
    payload = {
        "case_id": case_id,
        "score": score.to_dict(),
        "meta": meta or {},
        "events": events,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path
