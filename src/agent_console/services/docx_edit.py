"""Validate and apply `edit_docx` operations.

Dry-run validation builds plaintext diffs. Apply mutates only
`word/document.xml` and rebuilds the package by copying every other zip
entry byte-for-byte. Re-validate at apply time from the tip — do not trust
in-memory XML from an earlier approval payload.

``replace`` splices a single ``w:t`` in place. Spans that cross a ``w:t``,
run, hyperlink, tab, or break boundary are rejected as ``multi_run_span``.
``rewrite`` is the only op that rebuilds paragraph text runs.
"""

from __future__ import annotations

import copy
import hashlib
import io
import re
import zipfile
from dataclasses import dataclass, field
from typing import Any
from xml.etree import ElementTree as ET

from agent_console.services.docx_blocks import Block, Manifest, content_hash

__all__ = [
    "BlockDiff",
    "EditOp",
    "FORMAT_LOSS_NOTE",
    "ValidationError",
    "ValidationResult",
    "apply_approved_payload",
    "apply_ops",
    "ops_from_payload",
    "package_entry_digests",
    "validate_ops",
]

_WORD_NS = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
_XML_NS = "{http://www.w3.org/XML/1998/namespace}"
_BLOCK_ID_RE = re.compile(r"^g(\d+):p_(\d{4})$")
_TEMP_ID_RE = re.compile(r"^new_(\d+)$")
_DOCUMENT_XML = "word/document.xml"


class ValidationError(ValueError):
    """Raised when an op cannot be applied to the tip manifest."""


@dataclass(frozen=True)
class EditOp:
    op: str  # replace | rewrite | insert | delete
    block_id: str | None = None
    old: str | None = None
    new: str | None = None
    content: str | None = None
    hash: str | None = None
    relative_to: str | None = None
    position: str | None = None  # before | after
    new_id: str | None = None  # optional temp id for insert
    # Required when rewrite would flatten mixed inline formatting.
    allow_format_loss: bool = False


@dataclass(frozen=True)
class BlockDiff:
    block_id: str
    before: str
    after: str


@dataclass
class ValidationResult:
    ok: bool = True
    diffs: list[BlockDiff] = field(default_factory=list)
    temp_id_map: dict[str, str] = field(default_factory=dict)

    def plaintext(self) -> str:
        lines: list[str] = []
        for d in self.diffs:
            lines.append(f"### {d.block_id}")
            lines.append(f"- {d.before}")
            lines.append(f"+ {d.after}")
        return "\n".join(lines)


@dataclass(frozen=True)
class _CharLoc:
    """One character of joined paragraph text that lives inside a ``w:t``."""

    run: ET.Element
    t_node: ET.Element
    offset: int


def _parse_generation(block_id: str) -> int | None:
    match = _BLOCK_ID_RE.match(block_id)
    return int(match.group(1)) if match else None


def _is_temp_id(block_id: str) -> bool:
    return bool(_TEMP_ID_RE.match(block_id))


def _require_block(manifest: Manifest, block_id: str) -> Block:
    gen = _parse_generation(block_id)
    if gen is None or gen != manifest.generation:
        raise ValidationError(
            f"block id {block_id!r} is not from generation g{manifest.generation}; "
            "re-read the document and use current ids"
        )
    for block in manifest.blocks:
        if block.id == block_id:
            return block
    raise ValidationError(f"unknown block id {block_id!r}; re-read the document")


def _reject_temp_as_target(block_id: str | None) -> None:
    if block_id and _is_temp_id(block_id):
        raise ValidationError(
            f"temp id {block_id!r} cannot be the target of replace/rewrite/delete; "
            "only insert may declare and relative_to may reference temp ids"
        )
    if block_id and block_id.startswith("g") and ":new_" in block_id:
        raise ValidationError(
            f"temp IDs don't take a generation (got {block_id!r}); use new_<digits>"
        )


def _parse_new_id(raw: str | None, *, insert_seq: int, declared: set[str]) -> str:
    if raw is None or raw == "":
        candidate = f"new_{insert_seq}"
        while candidate in declared:
            insert_seq += 1
            candidate = f"new_{insert_seq}"
        return candidate
    if _is_temp_id(raw):
        if raw in declared:
            raise ValidationError(f"duplicate temp id {raw!r}")
        return raw
    if _BLOCK_ID_RE.match(raw) or ":new_" in raw:
        raise ValidationError(
            f"temp IDs don't take a generation (got {raw!r}); use new_<digits>"
        )
    raise ValidationError(
        f"insert new_id must match new_<digits> (got {raw!r})"
    )


def _resolve_relative_to(
    relative_to: str, *, manifest: Manifest, declared: set[str]
) -> None:
    if _is_temp_id(relative_to):
        if relative_to not in declared:
            raise ValidationError(
                f"forward or unknown temp id {relative_to!r}; declare it with "
                "new_id on an earlier insert in this batch"
            )
        return
    if relative_to.startswith("g") and ":new_" in relative_to:
        raise ValidationError(
            f"temp IDs don't take a generation (got {relative_to!r}); use new_<digits>"
        )
    _require_block(manifest, relative_to)


def _find_match_span(text: str, old: str) -> tuple[int, int]:
    """Return ``[start, end)`` of the single match for ``old`` in ``text``."""
    if not old:
        raise ValidationError("replace old text must be non-empty")
    exact_count = text.count(old)
    if exact_count == 1:
        start = text.index(old)
        return start, start + len(old)
    if exact_count > 1:
        raise ValidationError(
            f"replace old text has {exact_count} matches; refine old or use count later"
        )
    pattern = re.compile(re.escape(old), re.IGNORECASE)
    matches = list(pattern.finditer(text))
    if len(matches) == 0:
        raise ValidationError("replace old text has 0 matches in block")
    if len(matches) > 1:
        raise ValidationError(
            f"replace old text has {len(matches)} matches; refine old or use count later"
        )
    m = matches[0]
    return m.start(), m.end()


def _replace_once(text: str, old: str, new: str) -> str:
    start, end = _find_match_span(text, old)
    return text[:start] + new + text[end:]


def _paragraph_parent_map(paragraph: ET.Element) -> dict[ET.Element, ET.Element]:
    parents: dict[ET.Element, ET.Element] = {}
    for parent in paragraph.iter():
        for child in parent:
            parents[child] = parent
    return parents


def _owning_run(
    t_node: ET.Element, parents: dict[ET.Element, ET.Element]
) -> ET.Element | None:
    el: ET.Element | None = t_node
    while el is not None:
        if el.tag == f"{_WORD_NS}r":
            return el
        el = parents.get(el)
    return None


def _build_char_map(
    paragraph: ET.Element,
) -> tuple[str, list[_CharLoc | None]]:
    """Joined paragraph text (pre-strip) and per-character locations.

    Join rules match ``docx_blocks.parse_document_xml`` (``w:t`` / ``w:tab`` /
    ``w:br``). Characters that are not inside a ``w:t`` (tabs, breaks) map to
    ``None`` and cannot be spliced.
    """
    parents = _paragraph_parent_map(paragraph)
    locs: list[_CharLoc | None] = []
    parts: list[str] = []
    for node in paragraph.iter():
        tag = node.tag
        if tag == f"{_WORD_NS}t":
            text = node.text or ""
            run = _owning_run(node, parents)
            if run is None:
                for _ch in text:
                    parts.append(_ch)
                    locs.append(None)
                continue
            for offset, ch in enumerate(text):
                parts.append(ch)
                locs.append(_CharLoc(run=run, t_node=node, offset=offset))
        elif tag == f"{_WORD_NS}tab":
            parts.append("\t")
            locs.append(None)
        elif tag == f"{_WORD_NS}br":
            parts.append("\n")
            locs.append(None)
    return "".join(parts), locs


def _stripped_span(
    raw: str, locs: list[_CharLoc | None], block_text: str, start: int, end: int
) -> list[_CharLoc | None]:
    """Map a ``[start, end)`` span in stripped ``block_text`` onto char locs."""
    stripped = raw.strip()
    if stripped != block_text:
        raise ValidationError(
            "paragraph text map does not match manifest; re-read the document"
        )
    left = len(raw) - len(raw.lstrip())
    return locs[left + start : left + end]


def _assert_single_t_span(span_locs: list[_CharLoc | None]) -> _CharLoc:
    """Require every matched character to live in the same ``w:t``."""
    if not span_locs:
        raise ValidationError("multi_run_span: empty match")
    if any(loc is None for loc in span_locs):
        raise ValidationError(
            "multi_run_span: replace would cross a tab or line break; "
            "narrow old or use rewrite with care"
        )
    typed = [loc for loc in span_locs if loc is not None]
    first = typed[0]
    if any(loc.t_node is not first.t_node for loc in typed):
        raise ValidationError(
            "multi_run_span: replace crosses a w:t, run, or hyperlink boundary; "
            "narrow old so it sits inside one run, or wait for identical-rPr merge"
        )
    # Contiguous offsets inside that w:t.
    offsets = [loc.offset for loc in typed]
    if offsets != list(range(offsets[0], offsets[0] + len(offsets))):
        raise ValidationError(
            "multi_run_span: replace match is not contiguous inside one w:t"
        )
    return first


def _check_replace_in_paragraph(
    paragraph: ET.Element, block_text: str, old: str
) -> None:
    """Raise ``multi_run_span`` unless ``old`` sits entirely inside one ``w:t``."""
    raw, locs = _build_char_map(paragraph)
    start, end = _find_match_span(block_text, old)
    span = _stripped_span(raw, locs, block_text, start, end)
    _assert_single_t_span(span)


def _splice_replace_in_paragraph(
    paragraph: ET.Element, block_text: str, old: str, new: str
) -> str:
    """Splice ``new`` into the single matching ``w:t``; return new block text."""
    raw, locs = _build_char_map(paragraph)
    start, end = _find_match_span(block_text, old)
    span = _stripped_span(raw, locs, block_text, start, end)
    first = _assert_single_t_span(span)
    t_node = first.t_node
    text = t_node.text or ""
    t_start = first.offset
    t_end = span[-1].offset + 1  # type: ignore[union-attr]
    updated = text[:t_start] + new + text[t_end:]
    t_node.text = updated
    if updated[:1].isspace() or (updated and updated[-1:].isspace()):
        t_node.set(f"{_XML_NS}space", "preserve")
    elif f"{_XML_NS}space" in t_node.attrib and not (
        updated[:1].isspace() or (updated and updated[-1:].isspace())
    ):
        # Keep preserve if still needed; otherwise leave as-is when Word set it.
        pass
    return block_text[:start] + new + block_text[end:]


def _paragraphs_and_root(data: bytes) -> tuple[list[ET.Element], ET.Element]:
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        document_xml = zf.read(_DOCUMENT_XML)
    root = ET.fromstring(document_xml)
    return list(root.iter(f"{_WORD_NS}p")), root


_FIELD_OR_REVISION_TAGS = (
    f"{_WORD_NS}fldChar",
    f"{_WORD_NS}fldSimple",
    f"{_WORD_NS}ins",
    f"{_WORD_NS}del",
)

FORMAT_LOSS_NOTE = (
    "This rewrite discards mixed inline formatting (bold, links, etc.)."
)


def _reject_field_or_revision(paragraph: ET.Element, block_id: str) -> None:
    """Phase 1: refuse edits inside fields or tracked changes."""
    for tag in _FIELD_OR_REVISION_TAGS:
        if next(paragraph.iter(tag), None) is not None:
            local = tag.rsplit("}", 1)[-1]
            raise ValidationError(
                f"refusing to edit {block_id}: paragraph contains w:{local} "
                "(fields and tracked changes are not editable yet); "
                "re-read and pick another block"
            )


def _rpr_fingerprint(run: ET.Element) -> str:
    rpr = run.find(f"{_WORD_NS}rPr")
    if rpr is None:
        return ""
    return ET.canonicalize(ET.tostring(rpr, encoding="unicode"))


def _iter_runs(paragraph: ET.Element) -> list[ET.Element]:
    runs: list[ET.Element] = []
    for child in paragraph:
        if child.tag == f"{_WORD_NS}r":
            runs.append(child)
        elif child.tag == f"{_WORD_NS}hyperlink":
            runs.extend(r for r in child if r.tag == f"{_WORD_NS}r")
    return runs


def _has_mixed_inline_formatting(paragraph: ET.Element) -> bool:
    """True when rewrite would discard distinct run formatting or hyperlinks."""
    if next(paragraph.iter(f"{_WORD_NS}hyperlink"), None) is not None:
        return True
    fingerprints = {_rpr_fingerprint(run) for run in _iter_runs(paragraph)}
    return len(fingerprints) > 1


def _require_editable_paragraph(
    paragraphs: list[ET.Element] | None, block: Block
) -> ET.Element | None:
    if paragraphs is None:
        return None
    paragraph = paragraphs[block.index]
    _reject_field_or_revision(paragraph, block.id)
    return paragraph


def validate_ops(
    manifest: Manifest, ops: list[EditOp], *, data: bytes | None = None
) -> ValidationResult:
    """Validate ops against the tip manifest and return plaintext diffs.

    When ``data`` is provided, ``replace`` ops are also checked against the
    paragraph XML so ``multi_run_span`` fails before the approval card is shown.
    Does not mutate XML or the manifest.
    """
    if not ops:
        raise ValidationError("no operations provided")

    paragraphs: list[ET.Element] | None = None
    if data is not None:
        paragraphs, _ = _paragraphs_and_root(data)
        if len(paragraphs) != len(manifest.blocks):
            raise ValidationError(
                f"manifest/paragraph count mismatch "
                f"({len(manifest.blocks)} vs {len(paragraphs)}); re-read the document"
            )

    diffs: list[BlockDiff] = []
    texts: dict[str, str] = {b.id: b.text for b in manifest.blocks}
    hashes: dict[str, str] = {b.id: b.content_hash for b in manifest.blocks}
    declared: set[str] = set()
    temp_id_map: dict[str, str] = {}
    next_id = manifest.next_id
    generation = manifest.generation
    insert_seq = 0

    for op in ops:
        kind = op.op
        if kind == "replace":
            if not op.block_id or op.old is None or op.new is None:
                raise ValidationError("replace requires block_id, old, and new")
            _reject_temp_as_target(op.block_id)
            block = _require_block(manifest, op.block_id)
            paragraph = _require_editable_paragraph(paragraphs, block)
            before = texts[block.id]
            after = _replace_once(before, op.old, op.new)
            if paragraph is not None:
                _check_replace_in_paragraph(paragraph, before, op.old)
            texts[block.id] = after
            diffs.append(BlockDiff(block_id=block.id, before=before, after=after))

        elif kind == "rewrite":
            if not op.block_id or op.content is None or not op.hash:
                raise ValidationError("rewrite requires block_id, content, and hash")
            _reject_temp_as_target(op.block_id)
            block = _require_block(manifest, op.block_id)
            paragraph = _require_editable_paragraph(paragraphs, block)
            if op.hash != hashes[block.id]:
                raise ValidationError(
                    f"stale hash for {block.id}: expected {hashes[block.id]}, "
                    f"got {op.hash}; re-read the document"
                )
            if paragraph is not None and _has_mixed_inline_formatting(paragraph):
                if not op.allow_format_loss:
                    raise ValidationError(
                        f"rewrite of {block.id} would discard mixed inline formatting; "
                        "set allow_format_loss to true to confirm, or use replace "
                        "inside a single run"
                    )
            before = texts[block.id]
            after = op.content
            texts[block.id] = after
            diffs.append(BlockDiff(block_id=block.id, before=before, after=after))

        elif kind == "delete":
            if not op.block_id or not op.hash:
                raise ValidationError("delete requires block_id and hash")
            _reject_temp_as_target(op.block_id)
            block = _require_block(manifest, op.block_id)
            _require_editable_paragraph(paragraphs, block)
            if op.hash != hashes[block.id]:
                raise ValidationError(
                    f"stale hash for {block.id}: expected {hashes[block.id]}, "
                    f"got {op.hash}; re-read the document"
                )
            before = texts[block.id]
            texts[block.id] = ""
            diffs.append(BlockDiff(block_id=block.id, before=before, after=""))

        elif kind == "insert":
            if not op.relative_to or op.content is None:
                raise ValidationError("insert requires relative_to and content")
            position = op.position or "after"
            if position not in ("before", "after"):
                raise ValidationError("insert position must be 'before' or 'after'")
            _resolve_relative_to(op.relative_to, manifest=manifest, declared=declared)
            insert_seq += 1
            temp_id = _parse_new_id(op.new_id, insert_seq=insert_seq, declared=declared)
            declared.add(temp_id)
            real_id = f"g{generation}:p_{next_id:04d}"
            next_id += 1
            temp_id_map[temp_id] = real_id
            texts[temp_id] = op.content
            texts[real_id] = op.content
            diffs.append(BlockDiff(block_id=real_id, before="", after=op.content))

        else:
            raise ValidationError(f"unknown op {kind!r}")

    return ValidationResult(ok=True, diffs=diffs, temp_id_map=temp_id_map)


def package_entry_digests(data: bytes) -> dict[str, str]:
    """SHA-256 of every zip member — used to prove only document.xml changed."""
    digests: dict[str, str] = {}
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        for info in zf.infolist():
            digests[info.filename] = hashlib.sha256(zf.read(info.filename)).hexdigest()
    return digests


def _parent_map(root: ET.Element) -> dict[ET.Element, ET.Element]:
    parents: dict[ET.Element, ET.Element] = {}
    for parent in root.iter():
        for child in parent:
            parents[child] = parent
    return parents


def _paragraph_has_sect_pr(paragraph: ET.Element) -> bool:
    return next(paragraph.iter(f"{_WORD_NS}sectPr"), None) is not None


def _is_sole_paragraph_in_table_cell(
    paragraph: ET.Element, parent: ET.Element
) -> bool:
    if parent.tag != f"{_WORD_NS}tc":
        return False
    siblings = [c for c in parent if c.tag == f"{_WORD_NS}p"]
    return len(siblings) == 1


def _first_run_rpr(paragraph: ET.Element) -> ET.Element | None:
    for child in paragraph:
        if child.tag == f"{_WORD_NS}r":
            rpr = child.find(f"{_WORD_NS}rPr")
            return copy.deepcopy(rpr) if rpr is not None else None
        if child.tag == f"{_WORD_NS}hyperlink":
            for run in child:
                if run.tag == f"{_WORD_NS}r":
                    rpr = run.find(f"{_WORD_NS}rPr")
                    return copy.deepcopy(rpr) if rpr is not None else None
    return None


def _set_paragraph_text(paragraph: ET.Element, text: str) -> None:
    """Rewrite paragraph body text for ``rewrite`` only.

    Keeps ``pPr`` and non-run markers (bookmarks, comment ranges). Removes
    existing ``w:r`` / ``w:hyperlink`` children and writes new runs that carry
    the first prior run's ``rPr`` when present. ``\\n`` becomes ``w:br``.
    """
    first_rpr = _first_run_rpr(paragraph)
    for child in list(paragraph):
        if child.tag in {f"{_WORD_NS}r", f"{_WORD_NS}hyperlink"}:
            paragraph.remove(child)

    parts = text.split("\n")
    for index, part in enumerate(parts):
        run = ET.SubElement(paragraph, f"{_WORD_NS}r")
        if first_rpr is not None:
            run.insert(0, copy.deepcopy(first_rpr))
        if index > 0:
            ET.SubElement(run, f"{_WORD_NS}br")
        node = ET.SubElement(run, f"{_WORD_NS}t")
        node.text = part
        if part[:1].isspace() or (part and part[-1:].isspace()):
            node.set(f"{_XML_NS}space", "preserve")


def _make_paragraph(text: str) -> ET.Element:
    paragraph = ET.Element(f"{_WORD_NS}p")
    _set_paragraph_text(paragraph, text)
    return paragraph


def _rewrite_package(data: bytes, document_xml: bytes) -> bytes:
    """Copy every zip entry unchanged except `word/document.xml`."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(data), "r") as src:
        with zipfile.ZipFile(buffer, "w") as dst:
            for info in src.infolist():
                payload = src.read(info.filename)
                if info.filename == _DOCUMENT_XML:
                    payload = document_xml
                copied = zipfile.ZipInfo(filename=info.filename, date_time=info.date_time)
                copied.compress_type = info.compress_type
                copied.external_attr = info.external_attr
                copied.create_system = info.create_system
                dst.writestr(copied, payload)
    return buffer.getvalue()


def apply_ops(
    data: bytes, manifest: Manifest, ops: list[EditOp]
) -> tuple[bytes, Manifest, list[BlockDiff]]:
    """Apply validated ops; return new package bytes, carry-forward manifest, diffs.

    Callers must re-build `manifest` from the tip immediately before this — never
    reuse a parsed document stashed in an approval payload.
    """
    result = validate_ops(manifest, ops, data=data)

    paragraphs, root = _paragraphs_and_root(data)
    if len(paragraphs) != len(manifest.blocks):
        raise ValidationError(
            f"manifest/paragraph count mismatch "
            f"({len(manifest.blocks)} vs {len(paragraphs)}); re-read the document"
        )

    id_to_el: dict[str, ET.Element] = {
        block.id: paragraphs[block.index] for block in manifest.blocks
    }
    parents = _parent_map(root)
    order = [block.id for block in manifest.blocks]
    texts = {block.id: block.text for block in manifest.blocks}
    next_id = manifest.next_id
    generation = manifest.generation
    apply_diffs: list[BlockDiff] = []
    temp_id_map: dict[str, str] = {}
    insert_seq = 0
    declared: set[str] = set()
    # Real IDs assigned in operation order (not document order).
    temps_in_op_order: list[str] = []

    for op in ops:
        if op.op == "replace":
            assert op.block_id and op.old is not None and op.new is not None
            before = texts[op.block_id]
            after = _splice_replace_in_paragraph(
                id_to_el[op.block_id], before, op.old, op.new
            )
            texts[op.block_id] = after
            apply_diffs.append(BlockDiff(block_id=op.block_id, before=before, after=after))

        elif op.op == "rewrite":
            assert op.block_id and op.content is not None
            before = texts[op.block_id]
            after = op.content
            _set_paragraph_text(id_to_el[op.block_id], after)
            texts[op.block_id] = after
            apply_diffs.append(BlockDiff(block_id=op.block_id, before=before, after=after))

        elif op.op == "delete":
            assert op.block_id
            el = id_to_el[op.block_id]
            parent = parents[el]
            if _paragraph_has_sect_pr(el):
                raise ValidationError(
                    f"refusing to delete {op.block_id}: paragraph holds sectPr "
                    "(removing it corrupts the document)"
                )
            if _is_sole_paragraph_in_table_cell(el, parent):
                raise ValidationError(
                    f"refusing to delete {op.block_id}: it is the only paragraph "
                    "in its table cell"
                )
            parent.remove(el)
            before = texts[op.block_id]
            del id_to_el[op.block_id]
            del texts[op.block_id]
            order.remove(op.block_id)
            apply_diffs.append(BlockDiff(block_id=op.block_id, before=before, after=""))

        elif op.op == "insert":
            assert op.relative_to and op.content is not None
            position = op.position or "after"
            insert_seq += 1
            temp_id = _parse_new_id(op.new_id, insert_seq=insert_seq, declared=declared)
            declared.add(temp_id)
            if op.relative_to not in id_to_el:
                raise ValidationError(
                    f"unknown relative_to {op.relative_to!r}; re-read the document"
                )
            anchor = id_to_el[op.relative_to]
            parent = parents[anchor]
            new_el = _make_paragraph(op.content)
            children = list(parent)
            anchor_idx = children.index(anchor)
            insert_at = anchor_idx if position == "before" else anchor_idx + 1
            if (
                position == "after"
                and parent.tag == f"{_WORD_NS}body"
                and _paragraph_has_sect_pr(anchor)
            ):
                insert_at = anchor_idx
            elif position == "after" and parent.tag == f"{_WORD_NS}body":
                following = (
                    children[anchor_idx + 1 :] if anchor_idx + 1 < len(children) else []
                )
                if any(c.tag == f"{_WORD_NS}sectPr" for c in following):
                    insert_at = anchor_idx + 1
            parent.insert(insert_at, new_el)
            parents[new_el] = parent
            id_to_el[temp_id] = new_el
            texts[temp_id] = op.content
            if op.relative_to not in order:
                raise ValidationError(
                    f"relative_to {op.relative_to!r} missing from block order"
                )
            rel_idx = order.index(op.relative_to)
            order_at = rel_idx if position == "before" else rel_idx + 1
            if (
                position == "after"
                and _paragraph_has_sect_pr(anchor)
                and parent.tag == f"{_WORD_NS}body"
            ):
                order_at = rel_idx
            order.insert(order_at, temp_id)
            temps_in_op_order.append(temp_id)
            apply_diffs.append(BlockDiff(block_id=temp_id, before="", after=op.content))

    # Commit: assign real IDs from next_id in *operation* order.
    for temp_id in temps_in_op_order:
        real_id = f"g{generation}:p_{next_id:04d}"
        next_id += 1
        temp_id_map[temp_id] = real_id
        el = id_to_el.pop(temp_id)
        id_to_el[real_id] = el
        texts[real_id] = texts.pop(temp_id)
        order[order.index(temp_id)] = real_id

    apply_diffs = [
        BlockDiff(
            block_id=temp_id_map.get(d.block_id, d.block_id),
            before=d.before,
            after=d.after,
        )
        for d in apply_diffs
    ]

    new_xml = ET.tostring(root, encoding="utf-8", xml_declaration=True)
    out = _rewrite_package(data, new_xml)
    new_blocks = tuple(
        Block(
            id=block_id,
            text=texts[block_id],
            content_hash=content_hash(texts[block_id]),
            index=i,
        )
        for i, block_id in enumerate(order)
    )
    new_manifest = Manifest(
        generation=generation, next_id=next_id, blocks=new_blocks
    )
    assert len(apply_diffs) == len(result.diffs)
    # Validate and apply must agree on real IDs for inserts.
    assert [d.block_id for d in apply_diffs] == [d.block_id for d in result.diffs]
    return out, new_manifest, apply_diffs


def ops_from_payload(payload: dict[str, Any]) -> list[EditOp]:
    """Rebuild EditOp list from a JSON approval payload."""
    raw_ops = payload.get("operations") or []
    if not isinstance(raw_ops, list) or not raw_ops:
        raise ValidationError("approval payload has no operations")
    ops: list[EditOp] = []
    for item in raw_ops:
        if not isinstance(item, dict):
            raise ValidationError("invalid operation in approval payload")
        ops.append(
            EditOp(
                op=str(item.get("op") or ""),
                block_id=item.get("block_id"),
                old=item.get("old"),
                new=item.get("new"),
                content=item.get("content"),
                hash=item.get("hash"),
                relative_to=item.get("relative_to"),
                position=item.get("position"),
                new_id=item.get("new_id"),
                allow_format_loss=bool(item.get("allow_format_loss")),
            )
        )
    return ops


def apply_approved_payload(
    *,
    broker: Any,
    conversation_id: str,
    call_id: str,
    data: bytes,
    manifest: Manifest,
) -> tuple[bytes, Manifest, list[BlockDiff]]:
    """Consume a single-use approval payload and apply it to tip bytes.

    A second call with the same ids is rejected — insert replay would otherwise
    pass revalidation and duplicate content.
    """
    payload = broker.take_payload(conversation_id, call_id)
    if payload is None:
        raise ValidationError(
            "approval payload missing, expired, or already applied; "
            "re-read and propose the edit again"
        )
    return apply_ops(data, manifest, ops_from_payload(payload))
