"""Validate and apply `edit_docx` operations.

Dry-run validation builds plaintext diffs. Apply mutates only
`word/document.xml` and rebuilds the package by copying every other zip
entry byte-for-byte. Re-validate at apply time from the tip — do not trust
in-memory XML from an earlier approval payload.
"""

from __future__ import annotations

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


@dataclass(frozen=True)
class BlockDiff:
    block_id: str
    before: str
    after: str


@dataclass
class ValidationResult:
    ok: bool = True
    diffs: list[BlockDiff] = field(default_factory=list)

    def plaintext(self) -> str:
        lines: list[str] = []
        for d in self.diffs:
            lines.append(f"### {d.block_id}")
            lines.append(f"- {d.before}")
            lines.append(f"+ {d.after}")
        return "\n".join(lines)


def _parse_generation(block_id: str) -> int | None:
    match = _BLOCK_ID_RE.match(block_id)
    return int(match.group(1)) if match else None


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


def _replace_once(text: str, old: str, new: str) -> str:
    """Exact Unicode; Latin letters match case-insensitively for the find."""
    if not old:
        raise ValidationError("replace old text must be non-empty")
    exact_count = text.count(old)
    if exact_count == 1:
        return text.replace(old, new, 1)
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
    return text[: m.start()] + new + text[m.end() :]


def validate_ops(manifest: Manifest, ops: list[EditOp]) -> ValidationResult:
    """Validate ops against the tip manifest and return plaintext diffs.

    Does not mutate XML or the manifest.
    """
    if not ops:
        raise ValidationError("no operations provided")

    diffs: list[BlockDiff] = []
    texts: dict[str, str] = {b.id: b.text for b in manifest.blocks}
    hashes: dict[str, str] = {b.id: b.content_hash for b in manifest.blocks}
    insert_seq = 0

    for op in ops:
        kind = op.op
        if kind == "replace":
            if not op.block_id or op.old is None or op.new is None:
                raise ValidationError("replace requires block_id, old, and new")
            block = _require_block(manifest, op.block_id)
            before = texts[block.id]
            after = _replace_once(before, op.old, op.new)
            texts[block.id] = after
            diffs.append(BlockDiff(block_id=block.id, before=before, after=after))

        elif kind == "rewrite":
            if not op.block_id or op.content is None or not op.hash:
                raise ValidationError("rewrite requires block_id, content, and hash")
            block = _require_block(manifest, op.block_id)
            if op.hash != hashes[block.id]:
                raise ValidationError(
                    f"stale hash for {block.id}: expected {hashes[block.id]}, "
                    f"got {op.hash}; re-read the document"
                )
            before = texts[block.id]
            after = op.content
            texts[block.id] = after
            diffs.append(BlockDiff(block_id=block.id, before=before, after=after))

        elif kind == "delete":
            if not op.block_id or not op.hash:
                raise ValidationError("delete requires block_id and hash")
            block = _require_block(manifest, op.block_id)
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
            _require_block(manifest, op.relative_to)
            insert_seq += 1
            temp_id = op.new_id or f"new_{insert_seq}"
            diffs.append(BlockDiff(block_id=temp_id, before="", after=op.content))

        else:
            raise ValidationError(f"unknown op {kind!r}")

    return ValidationResult(ok=True, diffs=diffs)


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


def _set_paragraph_text(paragraph: ET.Element, text: str) -> None:
    """Write plain text; ``\\n`` becomes ``w:br``; leading/trailing spaces preserved.

    ElementTree escapes ``<>&`` on serialize. Existing runs/hyperlinks are replaced
    so we never leave literal newlines inside ``w:t``.
    """
    for child in list(paragraph):
        if child.tag in {f"{_WORD_NS}r", f"{_WORD_NS}hyperlink"}:
            paragraph.remove(child)

    parts = text.split("\n")
    for index, part in enumerate(parts):
        run = ET.SubElement(paragraph, f"{_WORD_NS}r")
        if index > 0:
            ET.SubElement(run, f"{_WORD_NS}br")
        node = ET.SubElement(run, f"{_WORD_NS}t")
        node.text = part
        if part[:1].isspace() or part[-1:].isspace():
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
    result = validate_ops(manifest, ops)

    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        document_xml = zf.read(_DOCUMENT_XML)
    root = ET.fromstring(document_xml)
    paragraphs = list(root.iter(f"{_WORD_NS}p"))
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

    for op in ops:
        if op.op == "replace":
            assert op.block_id and op.old is not None and op.new is not None
            before = texts[op.block_id]
            after = _replace_once(before, op.old, op.new)
            _set_paragraph_text(id_to_el[op.block_id], after)
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
            anchor = id_to_el[op.relative_to]
            parent = parents[anchor]
            new_el = _make_paragraph(op.content)
            children = list(parent)
            anchor_idx = children.index(anchor)
            insert_at = anchor_idx if position == "before" else anchor_idx + 1
            # Keep body-level or paragraph-level sectPr after all paragraphs.
            if (
                position == "after"
                and parent.tag == f"{_WORD_NS}body"
                and _paragraph_has_sect_pr(anchor)
            ):
                insert_at = anchor_idx
            elif position == "after" and parent.tag == f"{_WORD_NS}body":
                # python-docx puts sectPr as a direct body child after the last p.
                following = children[anchor_idx + 1 :] if anchor_idx + 1 < len(children) else []
                if any(c.tag == f"{_WORD_NS}sectPr" for c in following):
                    # Insert still after anchor p; sectPr stays last among body kids.
                    insert_at = anchor_idx + 1
            parent.insert(insert_at, new_el)
            parents[new_el] = parent
            new_block_id = f"g{generation}:p_{next_id:04d}"
            next_id += 1
            id_to_el[new_block_id] = new_el
            texts[new_block_id] = op.content
            rel_idx = order.index(op.relative_to)
            order_at = rel_idx if position == "before" else rel_idx + 1
            if (
                position == "after"
                and _paragraph_has_sect_pr(anchor)
                and parent.tag == f"{_WORD_NS}body"
            ):
                order_at = rel_idx
            order.insert(order_at, new_block_id)
            apply_diffs.append(
                BlockDiff(block_id=new_block_id, before="", after=op.content)
            )

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
