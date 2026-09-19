"""Tests for server-built edit_docx approval cards."""

from __future__ import annotations

from agent_console.services.docx_approval import (
    build_approval_card,
    truncate_around_change,
    word_diff_segments,
)
from agent_console.services.docx_edit import BlockDiff, EditOp


def test_word_diff_highlights_replaced_token() -> None:
    before_segs, after_segs = word_diff_segments(
        "Due in 45 days.", "Due in 30 days."
    )
    assert any(s["kind"] == "delete" and "45" in s["text"] for s in before_segs)
    assert any(s["kind"] == "insert" and "30" in s["text"] for s in after_segs)


def test_html_in_document_stays_plain_text_in_card() -> None:
    evil = '<img onerror="alert(1)" src=x> payload'
    card = build_approval_card(
        file_name="Contract.docx",
        from_version=7,
        diffs=[BlockDiff(block_id="g1:p_0001", before=evil, after="safe")],
        ops=[EditOp(op="rewrite", block_id="g1:p_0001", content="safe", hash="abc")],
    )
    # Card carries the literal string — React must render as text, never HTML.
    assert card["changes"][0]["before"] == evil
    assert "<img" in card["changes"][0]["before"]
    assert "script" not in card  # no HTML wrapper fields


def test_arabic_before_after_preserved_for_dir_auto() -> None:
    before = "المدة ٤٥ يوماً"
    after = "المدة ٣٠ يوماً"
    card = build_approval_card(
        file_name="عقد.docx",
        from_version=1,
        diffs=[BlockDiff(block_id="g1:p_0001", before=before, after=after)],
        ops=[
            EditOp(
                op="replace",
                block_id="g1:p_0001",
                old="٤٥",
                new="٣٠",
            )
        ],
    )
    assert card["changes"][0]["before"] == before
    assert card["changes"][0]["after"] == after
    assert card["file_name"] == "عقد.docx"


def test_long_paragraph_truncated_around_change() -> None:
    prefix = "alpha " * 80
    suffix = " omega" * 80
    before = f"{prefix}OLD_TOKEN{suffix}"
    after = f"{prefix}NEW_TOKEN{suffix}"
    b_out, a_out = truncate_around_change(before, after)
    assert "OLD_TOKEN" in b_out
    assert "NEW_TOKEN" in a_out
    assert b_out.startswith("…") or len(b_out) < len(before)
    assert len(b_out) < len(before)


def test_batch_of_50_changes_is_summarized() -> None:
    diffs = [
        BlockDiff(block_id=f"g1:p_{i:04d}", before="a", after="b")
        for i in range(1, 51)
    ]
    ops = [
        EditOp(op="rewrite", block_id=d.block_id, content="b", hash="x") for d in diffs
    ]
    card = build_approval_card(
        file_name="Big.docx",
        from_version=3,
        diffs=diffs,
        ops=ops,
    )
    assert card["change_count"] == 50
    assert len(card["changes"]) < 50
    assert card["omitted_count"] == 50 - len(card["changes"])
    assert card["from_version"] == 3
    assert card["to_version"] == 4
