"""Randomized multi-op sequences; optional corpus via DOCX_PARITY_DIR."""

from __future__ import annotations

import io
import os
import random
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest
from docx import Document

from agent_console.services.docx_blocks import assign_fresh_manifest, block_texts
from agent_console.services.docx_edit import (
    EditOp,
    ValidationError,
    apply_ops,
    package_entry_digests,
)

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def _minimal(*paragraphs: str) -> bytes:
    doc = Document()
    for text in paragraphs:
        doc.add_paragraph(text)
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def _iter_corpus() -> list[Path]:
    raw = os.environ.get("DOCX_PARITY_DIR", "")
    roots = [Path(p) for p in raw.split(os.pathsep) if p.strip()]
    out: list[Path] = []
    for root in roots:
        if not root.is_dir():
            continue
        for dirpath, dirnames, filenames in os.walk(root):
            rel = Path(dirpath).relative_to(root)
            depth = 0 if str(rel) == "." else len(rel.parts)
            if depth >= 2:
                dirnames.clear()
            for name in filenames:
                if name.endswith(".docx") and not name.startswith("~$"):
                    out.append(Path(dirpath) / name)
    return sorted(out)[:30]  # cap for CI time


def _safe_replace_targets(data: bytes, manifest) -> list[tuple[str, str]]:
    """(block_id, old) pairs that sit inside a single w:t and avoid fields."""
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        root = ET.fromstring(zf.read("word/document.xml"))
    paragraphs = list(root.iter(f"{W}p"))
    targets: list[tuple[str, str]] = []
    for block in manifest.blocks:
        if block.index >= len(paragraphs):
            continue
        p = paragraphs[block.index]
        if any(
            next(p.iter(tag), None) is not None
            for tag in (f"{W}fldChar", f"{W}fldSimple", f"{W}ins", f"{W}del")
        ):
            continue
        # Prefer a unique token of length >= 3 from a single w:t
        for t in p.iter(f"{W}t"):
            text = t.text or ""
            for word in text.split():
                if len(word) >= 3 and block.text.count(word) == 1:
                    targets.append((block.id, word))
                    break
    return targets


@pytest.mark.parametrize("seed", range(25))
def test_randomized_mixed_ops_preserve_package_and_ids(seed: int) -> None:
    rng = random.Random(seed)
    data = _minimal("Alpha", "Beta", "Gamma", "Delta")
    manifest = assign_fresh_manifest(data, generation=1)
    before_digests = package_entry_digests(data)

    ops: list[EditOp] = []
    # insert chain
    ops.append(
        EditOp(
            op="insert",
            relative_to="g1:p_0001",
            position="before",
            content=f"H{seed}",
            new_id="new_1",
        )
    )
    ops.append(
        EditOp(
            op="insert",
            relative_to="new_1",
            position="after",
            content=f"P{seed}",
            new_id="new_2",
        )
    )
    # replace on original Alpha (still g1:p_0001 after carry-forward apply)
    ops.append(EditOp(op="replace", block_id="g1:p_0001", old="Alpha", new=f"A{seed}"))
    # delete Gamma
    gamma = next(b for b in manifest.blocks if b.text == "Gamma")
    ops.append(EditOp(op="delete", block_id=gamma.id, hash=gamma.content_hash))
    # rewrite plain Delta (single formatting)
    delta = next(b for b in manifest.blocks if b.text == "Delta")
    if rng.random() < 0.5:
        ops.append(
            EditOp(
                op="rewrite",
                block_id=delta.id,
                content=f"D{seed}",
                hash=delta.content_hash,
            )
        )

    out, new_manifest, diffs = apply_ops(data, manifest, ops)
    after = package_entry_digests(out)
    assert set(before_digests) == set(after)
    assert [n for n in before_digests if before_digests[n] != after[n]] == [
        "word/document.xml"
    ]
    texts = block_texts(out)
    assert f"H{seed}" in texts and f"P{seed}" in texts
    assert f"A{seed}" in texts
    assert "Gamma" not in texts
    # IDs for surviving originals still present
    ids = {b.id for b in new_manifest.blocks}
    assert "g1:p_0001" in ids
    assert gamma.id not in ids
    assert len(diffs) == len(ops)


def test_randomized_replace_on_corpus_when_available() -> None:
    paths = _iter_corpus()
    if not paths:
        pytest.skip("DOCX_PARITY_DIR not set — no external corpus")
    failures: list[str] = []
    checked = 0
    for path in paths:
        try:
            data = path.read_bytes()
            manifest = assign_fresh_manifest(data, generation=1)
            targets = _safe_replace_targets(data, manifest)
            if not targets:
                continue
            block_id, old = targets[0]
            new = old[:-1] + ("X" if not old.endswith("X") else "Y")
            if new == old:
                continue
            before = package_entry_digests(data)
            out, _, _ = apply_ops(
                data,
                manifest,
                [EditOp(op="replace", block_id=block_id, old=old, new=new)],
            )
            after = package_entry_digests(out)
            changed = [n for n in before if before[n] != after[n]]
            if changed != ["word/document.xml"]:
                failures.append(f"{path}: changed {changed}")
            checked += 1
        except (ValidationError, ValueError, KeyError, OSError) as exc:
            failures.append(f"{path}: {exc}")
    assert checked > 0, "corpus had no replaceable single-run tokens"
    assert not failures, "\n".join(failures[:20])
