"""edit_docx e2e: fixture integrity (fast) + live agent suite (slow)."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from agent_console.services.docx_blocks import assign_fresh_manifest, block_texts
from agent_console.services.docx_edit import EditOp, ValidationError, apply_ops, validate_ops
from tests.edit_docx_e2e_corpus import CASES, all_fixtures, build_multi_run_span, build_tracked_changes
from tests.edit_docx_e2e_score import score_case

TRANSCRIPT_DIR = Path(__file__).parent / "fixtures" / "edit_docx_e2e" / "transcripts"


def test_e2e_corpus_builds_and_is_unique() -> None:
    fixtures = all_fixtures()
    assert len(fixtures) == len(CASES)
    assert len({c.id for c in CASES}) == len(CASES)


def test_multi_run_fixture_rejects_cross_format_span() -> None:
    name, data = build_multi_run_span()
    assert name.endswith(".docx")
    manifest = assign_fresh_manifest(data, generation=1)
    block = manifest.blocks[0]
    with pytest.raises(ValidationError, match="multi_run_span"):
        validate_ops(
            manifest,
            [
                EditOp(
                    op="replace",
                    block_id=block.id,
                    old="Effective 01-01-2026 until",
                    new="Effective 02-02-2026 until",
                )
            ],
            data=data,
        )
    # Shorter old inside the bold run should succeed.
    out, _, _ = apply_ops(
        data,
        manifest,
        [
            EditOp(
                op="replace",
                block_id=block.id,
                old="01-01-2026",
                new="02-02-2026",
            )
        ],
    )
    assert "02-02-2026" in block_texts(out)[0]


def test_tracked_fixture_rejects_clause_b() -> None:
    _, data = build_tracked_changes()
    manifest = assign_fresh_manifest(data, generation=1)
    clause_b = next(b for b in manifest.blocks if "Clause B" in b.text)
    with pytest.raises(ValidationError, match="ins"):
        validate_ops(
            manifest,
            [
                EditOp(
                    op="replace",
                    block_id=clause_b.id,
                    old="Clause B",
                    new="Clause B was revised",
                )
            ],
            data=data,
        )


def test_score_asks_for_ambiguous() -> None:
    case = next(c for c in CASES if c.id == "ambiguous_date")
    events = [
        {"type": "tool_call", "name": "read_uploaded_file", "arguments": "{}"},
        {
            "type": "tool_call",
            "name": "ask_user",
            "arguments": '{"question":"Which date?"}',
        },
        {"type": "text_delta", "text": "Which date should I change?"},
    ]
    score = score_case(case, events, tip_text="")
    assert score.passed
    assert score.correct_tool_path


def test_score_flags_forbidden_write_file() -> None:
    case = next(c for c in CASES if c.id == "replace_en")
    events = [
        {"type": "tool_call", "name": "write_file", "arguments": "{}"},
        {"type": "text_delta", "text": "done"},
    ]
    score = score_case(case, events, tip_text="Status: Final\nOwner: Alice")
    assert not score.no_forbidden_fallback
    assert not score.passed


@pytest.mark.slow
@pytest.mark.skipif(
    os.environ.get("EDIT_DOCX_E2E") != "1",
    reason="Set EDIT_DOCX_E2E=1 to run live agent regression",
)
def test_live_edit_docx_e2e_suite() -> None:
    """Delegates to the script; fails if any case score.passed is false."""
    import json
    import subprocess
    import sys

    env = os.environ.copy()
    env["EDIT_DOCX_E2E"] = "1"
    proc = subprocess.run(
        [sys.executable, str(Path(__file__).parents[1] / "scripts" / "run_edit_docx_e2e.py")],
        cwd=str(Path(__file__).parents[1]),
        env=env,
        check=False,
    )
    summary = TRANSCRIPT_DIR / "summary.json"
    assert summary.is_file(), "runner did not write summary.json"
    results = json.loads(summary.read_text(encoding="utf-8"))
    failed = [r for r in results if not r.get("score", {}).get("passed")]
    assert proc.returncode == 0 and not failed, failed
