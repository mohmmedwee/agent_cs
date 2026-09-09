"""Turning uploaded bytes into text the model can read.

Office formats are containers, not text, so "is this UTF-8?" is the wrong
question to ask of an upload. This module answers the useful one: can we get
readable text out of it, and how.

Extraction is stdlib-only by design — the server may run on an isolated
network where installing a parser is not an option.
"""

import io
import re
import zipfile
from xml.etree import ElementTree

__all__ = ["extract_text", "looks_like_text"]

_WORD_NS = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def looks_like_text(data: bytes) -> bool:
    """True if the bytes decode as UTF-8 and carry no NUL."""
    if b"\x00" in data:
        return False
    try:
        data.decode("utf-8")
    except UnicodeDecodeError:
        return False
    return True


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


def extract_text(data: bytes, name: str) -> str | None:
    """Readable text for an upload, or None if we have no way to read it."""
    if looks_like_text(data):
        return data.decode("utf-8")
    if name.lower().endswith(".docx"):
        return _docx_text(data)
    return None
