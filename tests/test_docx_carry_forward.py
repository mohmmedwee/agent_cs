"""Carry-forward manifests and generation bumps after convert / run_python."""

from __future__ import annotations

import io

import pytest
from docx import Document

from agent_console.services.docx_blocks import assign_fresh_manifest, block_texts
from agent_console.services.docx_edit import EditOp, ValidationError, apply_ops, validate_ops


def _minimal_docx(*paragraphs: str) -> bytes:
    doc = Document()
    for text in paragraphs:
        doc.add_paragraph(text)
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def test_insert_above_then_edit_keeps_old_id_on_original_paragraph() -> None:
    """Carry-forward: insert shifts order but g1:p_0001 still names the old text."""
    data = _minimal_docx("Alpha", "Beta", "Gamma")
    manifest = assign_fresh_manifest(data, generation=1)
    alpha_id = "g1:p_0001"
    assert manifest.blocks[0].text == "Alpha"

    out, carried, _ = apply_ops(
        data,
        manifest,
        [
            EditOp(
                op="insert",
                relative_to=alpha_id,
                position="before",
                content="NEW",
                new_id="new_1",
            )
        ],
    )
    assert block_texts(out)[:2] == ["NEW", "Alpha"]
    by_id = {b.id: b for b in carried.blocks}
    assert by_id[alpha_id].text == "Alpha"
    assert by_id[alpha_id].index == 1

    out2, carried2, diffs = apply_ops(
        out,
        carried,
        [EditOp(op="replace", block_id=alpha_id, old="Alpha", new="ALPHA")],
    )
    assert diffs[0].after == "ALPHA"
    assert block_texts(out2)[:2] == ["NEW", "ALPHA"]
    assert {b.id: b.text for b in carried2.blocks}[alpha_id] == "ALPHA"


def test_fresh_reassign_after_insert_would_point_at_wrong_paragraph() -> None:
    """Documents why persisted manifests matter: reassign maps p_0001 to NEW."""
    data = _minimal_docx("Alpha", "Beta")
    manifest = assign_fresh_manifest(data, generation=1)
    out, _, _ = apply_ops(
        data,
        manifest,
        [
            EditOp(
                op="insert",
                relative_to="g1:p_0001",
                position="before",
                content="NEW",
            )
        ],
    )
    reassigned = assign_fresh_manifest(out, generation=1)
    assert reassigned.blocks[0].text == "NEW"
    assert reassigned.blocks[0].id == "g1:p_0001"


def test_bumped_generation_rejects_old_ids_with_reread() -> None:
    """When generation advances, stale gN ids fail closed."""
    data = _minimal_docx("Hello")
    m2 = assign_fresh_manifest(data, generation=2)
    with pytest.raises(ValidationError, match="re-read"):
        validate_ops(
            m2,
            [EditOp(op="replace", block_id="g1:p_0001", old="Hello", new="Hi")],
            data=data,
        )


@pytest.mark.xfail(
    reason="convert must bump tip generation (slice 6); read/edit still use g1",
    strict=True,
)
def test_after_convert_rebuild_platform_bumps_generation() -> None:
    """Convert rebuilds tip bytes from markdown — old g1 ids must not rematch."""
    # Stand-in for "generation stored on tip after convert".
    # Today read_uploaded_file / edit_docx always assign_fresh(..., generation=1).
    generation_after_convert = 1
    assert generation_after_convert >= 2


@pytest.mark.xfail(
    reason="run_python DOCX save must bump tip generation (slice 6)",
    strict=True,
)
def test_after_run_python_docx_save_platform_bumps_generation() -> None:
    generation_after_run_python = 1
    assert generation_after_run_python >= 2
