"""DOCX body blocks: paragraph texts, generation-scoped IDs, and manifests.

Phase 1 foundation for `edit_docx`. Block texts use the same join rules as
`extraction._docx_text` (every body `w:p`, including table cells / SDTs).
IDs live on the platform manifest only — never written into OOXML.
"""

from __future__ import annotations

import hashlib
import io
import re
import zipfile
from dataclasses import dataclass
from xml.etree import ElementTree

__all__ = [
    "Block",
    "BlockHit",
    "Manifest",
    "assign_fresh_manifest",
    "block_texts",
    "content_hash",
    "format_annotated",
    "format_block_line",
    "parse_document_xml",
    "search_blocks",
]

_WORD_NS = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


@dataclass(frozen=True)
class Block:
    """One editable body paragraph in document order."""

    id: str
    text: str
    content_hash: str
    index: int


@dataclass(frozen=True)
class Manifest:
    """ID map for one DOCX version tip.

    `next_id` is the next local counter to assign (1-based). Never derive it
    from `max(existing)+1` — deletes must not recycle ids.
    """

    generation: int
    next_id: int
    blocks: tuple[Block, ...]


def content_hash(text: str) -> str:
    """Short stable hash of block plain text (shown as `h=…` in annotated reads)."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:8]


def parse_document_xml(document_xml: bytes) -> list[str]:
    """Plain text for every `w:p` in document order (same rules as `_docx_text`)."""
    root = ElementTree.fromstring(document_xml)
    lines: list[str] = []
    for paragraph in root.iter(f"{_WORD_NS}p"):
        parts: list[str] = []
        for node in paragraph.iter():
            tag = node.tag
            if tag == f"{_WORD_NS}t":
                parts.append(node.text or "")
            elif tag == f"{_WORD_NS}tab":
                parts.append("\t")
            elif tag == f"{_WORD_NS}br":
                parts.append("\n")
        lines.append("".join(parts).strip())
    return lines


def block_texts(data: bytes) -> list[str]:
    """Extract per-paragraph plain texts from a .docx package."""
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            document = archive.read("word/document.xml")
    except (zipfile.BadZipFile, KeyError) as exc:
        raise ValueError("not a readable .docx") from exc
    try:
        return parse_document_xml(document)
    except ElementTree.ParseError as exc:
        raise ValueError("invalid word/document.xml") from exc


def assign_fresh_manifest(data: bytes, *, generation: int = 1) -> Manifest:
    """Build a new-generation manifest with order-based ids `gN:p_####`."""
    if generation < 1:
        raise ValueError("generation must be >= 1")
    texts = block_texts(data)
    blocks: list[Block] = []
    for i, text in enumerate(texts, start=1):
        block_id = f"g{generation}:p_{i:04d}"
        blocks.append(
            Block(
                id=block_id,
                text=text,
                content_hash=content_hash(text),
                index=i - 1,
            )
        )
    return Manifest(
        generation=generation,
        next_id=len(texts) + 1,
        blocks=tuple(blocks),
    )


def format_block_line(block: Block) -> str:
    """One annotated line: `[g1:p_0142 h=a1b2c3d4] plain text`."""
    return f"[{block.id} h={block.content_hash}] {block.text}"


def format_annotated(manifest: Manifest) -> str:
    """Full annotated document body for `read_uploaded_file` on DOCX."""
    return "\n".join(format_block_line(b) for b in manifest.blocks)


@dataclass(frozen=True)
class BlockHit:
    block_id: str
    content_hash: str
    start: int
    end: int
    excerpt: str


def search_blocks(
    manifest: Manifest, needle: str, *, max_hits: int = 20
) -> list[BlockHit]:
    """Case-insensitive literal search over block plain texts."""
    if not needle:
        return []
    pattern = re.compile(re.escape(needle), re.IGNORECASE)
    hits: list[BlockHit] = []
    for block in manifest.blocks:
        for match in pattern.finditer(block.text):
            start, end = match.start(), match.end()
            left = max(0, start - 80)
            right = min(len(block.text), end + 80)
            excerpt = " ".join(block.text[left:right].split())
            hits.append(
                BlockHit(
                    block_id=block.id,
                    content_hash=block.content_hash,
                    start=start,
                    end=end,
                    excerpt=excerpt,
                )
            )
            if len(hits) >= max_hits:
                return hits
    return hits
