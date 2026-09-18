"""Turning uploaded bytes into text the model can read.

Office and PDF are containers, not plain UTF-8, so "does this decode?" is the
wrong question. This module answers the useful one: can we extract readable
text, and how.
"""

from __future__ import annotations

import io
import logging
import re
import zipfile
from pathlib import Path
from xml.etree import ElementTree

__all__ = [
    "docx_media_bytes",
    "docx_preview_markdown",
    "extract_text",
    "looks_like_text",
    "page_at_offset",
]

logger = logging.getLogger(__name__)

_WORD_NS = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
_A_NS = "{http://schemas.openxmlformats.org/drawingml/2006/main}"
_R_NS = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
_WP_NS = "{http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing}"
_PAGE_MARKER = re.compile(r"^--- Page (\d+) ---$", re.MULTILINE)


def looks_like_text(data: bytes) -> bool:
    """True if the bytes decode as UTF-8 and carry no NUL."""
    if b"\x00" in data:
        return False
    try:
        data.decode("utf-8")
    except UnicodeDecodeError:
        return False
    return True


def page_at_offset(content: str, offset: int) -> int | None:
    """Page number for a character offset when content uses `--- Page N ---` markers."""
    page: int | None = None
    for match in _PAGE_MARKER.finditer(content):
        if match.start() <= offset:
            page = int(match.group(1))
        else:
            break
    return page


def _docx_relationships(archive: zipfile.ZipFile) -> dict[str, str]:
    """Map relationship id → package path (e.g. word/media/image1.png)."""
    try:
        rels_xml = archive.read("word/_rels/document.xml.rels")
    except KeyError:
        return {}
    try:
        root = ElementTree.fromstring(rels_xml)
    except ElementTree.ParseError:
        return {}
    mapping: dict[str, str] = {}
    for node in root:
        if not node.tag.endswith("Relationship"):
            continue
        rid = node.attrib.get("Id")
        target = (node.attrib.get("Target") or "").replace("\\", "/")
        if not rid or not target:
            continue
        if target.startswith("/"):
            package_path = target.lstrip("/")
        else:
            # Relative to word/
            package_path = str(Path("word") / target)
        package_path = package_path.replace("\\", "/")
        while "/../" in package_path:
            package_path = re.sub(r"[^/]+/\.\./", "", package_path, count=1)
        if "/media/" in package_path or package_path.startswith("word/media/"):
            mapping[rid] = package_path
    return mapping


def _paragraph_preview_chunks(
    paragraph: ElementTree.Element, rels: dict[str, str]
) -> list[str]:
    """Text and image markdown markers for one Word paragraph, in order."""
    chunks: list[str] = []
    text_parts: list[str] = []

    def flush_text() -> None:
        nonlocal text_parts
        line = "".join(text_parts).strip()
        text_parts = []
        if line:
            chunks.append(line)

    alt_default = "Chart"
    for ancestor in paragraph.iter(f"{_WP_NS}docPr"):
        alt_default = (
            ancestor.attrib.get("descr") or ancestor.attrib.get("name") or alt_default
        )
        break

    for node in paragraph.iter():
        tag = node.tag
        if tag == f"{_WORD_NS}t":
            text_parts.append(node.text or "")
        elif tag == f"{_WORD_NS}tab":
            text_parts.append("\t")
        elif tag == f"{_WORD_NS}br":
            text_parts.append("\n")
        elif tag == f"{_A_NS}blip":
            flush_text()
            rid = node.attrib.get(f"{_R_NS}embed")
            target = rels.get(rid or "", "")
            media_name = Path(target).name if target else ""
            if media_name:
                chunks.append(f"![{alt_default}](media:{media_name})")
    flush_text()
    return chunks


def _docx_text(data: bytes) -> str | None:
    """Paragraph text from a Word document, in document order.

    Table cells are made of the same paragraph elements, so walking every `w:p`
    picks them up too — without trying to reconstruct the table layout.
    Images are omitted here so agent context stays small; use
    `docx_preview_markdown` for the UI preview.
    """
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            document = archive.read("word/document.xml")
    except (zipfile.BadZipFile, KeyError):
        return None

    try:
        root = ElementTree.fromstring(document)
    except ElementTree.ParseError:
        return None

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

    text = re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()
    return text or None


def docx_preview_markdown(data: bytes, file_id: str) -> str | None:
    """Markdown for the artifact pane, with embedded images as API media links."""
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            document = archive.read("word/document.xml")
            rels = _docx_relationships(archive)
    except (zipfile.BadZipFile, KeyError):
        return None

    try:
        root = ElementTree.fromstring(document)
    except ElementTree.ParseError:
        return None

    lines: list[str] = []
    for paragraph in root.iter(f"{_WORD_NS}p"):
        for chunk in _paragraph_preview_chunks(paragraph, rels):
            if chunk.startswith("![") and "(media:" in chunk:
                # Rewrite placeholder to a same-origin media URL.
                match = re.match(r"!\[([^\]]*)\]\(media:([^)]+)\)", chunk)
                if match:
                    alt, media = match.group(1), match.group(2)
                    lines.append(
                        f"![{alt}](/api/files/{file_id}/docx-media/{media})"
                    )
                else:
                    lines.append(chunk)
            else:
                lines.append(chunk)

    text = re.sub(r"\n{3,}", "\n\n", "\n\n".join(lines)).strip()
    return text or None


def docx_media_bytes(data: bytes, media_name: str) -> tuple[bytes, str] | None:
    """Return (bytes, content_type) for `word/media/{media_name}` inside a .docx."""
    safe = Path(media_name).name
    if not safe or safe != media_name or ".." in media_name:
        return None
    path = f"word/media/{safe}"
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            payload = archive.read(path)
    except (zipfile.BadZipFile, KeyError):
        return None
    content_type = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".gif": "image/gif",
        ".webp": "image/webp",
        ".bmp": "image/bmp",
    }.get(Path(safe).suffix.lower(), "application/octet-stream")
    return payload, content_type


def _pdf_text(data: bytes) -> str | None:
    """Per-page text from a PDF, with markers so search can cite a page."""
    try:
        from pypdf import PdfReader
    except ImportError:
        logger.warning("pypdf is not installed; PDF uploads stay unreadable")
        return None

    try:
        reader = PdfReader(io.BytesIO(data))
    except Exception:  # noqa: BLE001 — corrupt or encrypted PDFs
        return None

    sections: list[str] = []
    for index, page in enumerate(reader.pages, start=1):
        try:
            raw = page.extract_text() or ""
        except Exception:  # noqa: BLE001 — some pages fail individually
            raw = ""
        body = re.sub(r"\n{3,}", "\n\n", raw).strip()
        if not body:
            continue
        sections.append(f"--- Page {index} ---\n{body}")

    text = "\n\n".join(sections).strip()
    return text or None


def extract_text(data: bytes, name: str) -> str | None:
    """Readable text for an upload, or None if we have no way to read it."""
    if looks_like_text(data):
        return data.decode("utf-8")
    lower = name.lower()
    if lower.endswith(".docx"):
        return _docx_text(data)
    if lower.endswith(".pdf"):
        return _pdf_text(data)
    return None
