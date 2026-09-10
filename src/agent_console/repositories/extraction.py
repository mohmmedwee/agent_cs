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
from xml.etree import ElementTree

__all__ = ["extract_text", "looks_like_text", "page_at_offset"]

logger = logging.getLogger(__name__)

_WORD_NS = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
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


def _docx_text(data: bytes) -> str | None:
    """Paragraph text from a Word document, in document order.

    Table cells are made of the same paragraph elements, so walking every `w:p`
    picks them up too — without trying to reconstruct the table layout.
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
