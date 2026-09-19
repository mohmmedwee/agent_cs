"""Unit tests for edit_docx soak classification / summaries."""

from __future__ import annotations

import json
import logging

from agent_console.services.docx_soak import (
    SoakTracker,
    classify_edit_error,
    ops_summary,
)


def test_classify_multi_run_and_generation() -> None:
    assert classify_edit_error("Error: multi_run_span …") == "multi_run_span"
    assert (
        classify_edit_error(
            "Error: generation g1 does not match tip g2; re-read the document"
        )
        == "generation_mismatch"
    )
    assert classify_edit_error("Updated report.docx v1 → v2") is None


def test_ops_summary_no_document_text() -> None:
    raw = json.dumps(
        {
            "name": "report.docx",
            "generation": 2,
            "operations": [
                {"op": "replace", "old": "SECRET CLIENT TEXT", "new": "x"},
                {"op": "insert", "content": "more secrets"},
            ],
        }
    )
    summary = ops_summary(raw)
    blob = json.dumps(summary)
    assert "SECRET" not in blob
    assert summary["ops"] == ["replace", "insert"]
    assert summary["op_count"] == 2


def test_soak_tracker_logs_retry_and_fallback(caplog) -> None:
    caplog.set_level(logging.INFO, logger="agent_console.docx_soak")
    soak = SoakTracker(conversation_id="c1", user_id="u1")
    args = '{"name":"a.docx","operations":[{"op":"replace"}]}'
    soak.edit_proposed(args)
    soak.edit_result(args, "Error: multi_run_span crossing runs")
    soak.edit_proposed(args)
    soak.edit_result(args, "Updated a.docx v1 → v2 (1 change(s))")
    soak.tool_used("run_python", '{"code":"..."}')
    events = [json.loads(r.message) for r in caplog.records if r.name == "agent_console.docx_soak"]
    kinds = [e["event"] for e in events]
    assert "edit_docx_proposed" in kinds
    assert "edit_docx_error" in kinds
    assert "edit_docx_applied" in kinds
    err = next(e for e in events if e["event"] == "edit_docx_error")
    assert err["error_type"] == "multi_run_span"
    assert err["retry_index"] == 1
