"""On-disk storage for uploaded files.

Metadata lives in memory alongside the bytes on disk, which is enough for a
single-process server. Swap this class for a database-backed one when you add
multi-user support; nothing outside this module knows how storage works.
"""

import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from agent_console.models.files import StoredFile
from agent_console.repositories.extraction import extract_text

__all__ = ["FileRepository", "FileTooLargeError", "UnknownFileError"]


class UnknownFileError(LookupError):
    """No uploaded file matches the given id or name."""


class FileTooLargeError(ValueError):
    """The upload exceeded the configured size limit."""


class UnreadableFileError(ValueError):
    """The file is stored but we have no way to read it as text."""


def _safe_name(name: str) -> str:
    """Strip any directory component so an upload can't escape the store."""
    cleaned = unicodedata.normalize("NFC", name).replace("\\", "/")
    return Path(cleaned).name or "unnamed"


class FileRepository:
    def __init__(self, directory: Path, max_bytes: int) -> None:
        self._directory = directory
        self._max_bytes = max_bytes
        self._directory.mkdir(parents=True, exist_ok=True)
        self._index: dict[str, StoredFile] = {}

    def save(self, name: str, data: bytes, content_type: str | None = None) -> StoredFile:
        if len(data) > self._max_bytes:
            raise FileTooLargeError(
                f"{name} is {len(data)} bytes; the limit is {self._max_bytes}"
            )
        file_id = uuid4().hex[:12]
        (self._directory / file_id).write_bytes(data)
        record = StoredFile(
            id=file_id,
            name=_safe_name(name),
            size=len(data),
            content_type=content_type,
            uploaded_at=datetime.now(timezone.utc),
            # "Can the agent read this?", not "are these bytes UTF-8?" — a .docx
            # is binary but perfectly readable once unpacked.
            is_text=extract_text(data, _safe_name(name)) is not None,
        )
        self._index[file_id] = record
        return record

    def list(self) -> list[StoredFile]:
        return sorted(self._index.values(), key=lambda f: f.uploaded_at)

    def get(self, ref: str) -> StoredFile:
        """Look up by id, then by exact name — the model tends to use the name."""
        if ref in self._index:
            return self._index[ref]
        for record in self._index.values():
            if record.name == ref:
                return record
        raise UnknownFileError(f"no uploaded file matches {ref!r}")

    def raw_bytes(self, ref: str) -> bytes:
        """The stored bytes, for download."""
        return (self._directory / self.get(ref).id).read_bytes()

    def text(self, ref: str) -> str:
        """The file's full text. Raises if we have no way to read it."""
        record = self.get(ref)
        content = extract_text((self._directory / record.id).read_bytes(), record.name)
        if content is None:
            raise UnreadableFileError(
                f"{record.name} is not a format this server can read as text "
                "(plain text and .docx are supported)"
            )
        return content

    def read_text(self, ref: str, max_chars: int, offset: int = 0) -> str:
        """A window of the file's text.

        The window is explicit so a document longer than `max_chars` is paged
        through rather than silently cut off at the first screenful.
        """
        content = self.text(ref)
        total = len(content)
        start = max(0, min(offset, total))
        window = content[start : start + max_chars]
        end = start + len(window)

        if start == 0 and end == total:
            return window
        return (
            f"[characters {start}–{end} of {total}]\n\n{window}"
            + (
                f"\n\n[{total - end} characters remain — call again with offset={end}]"
                if end < total
                else ""
            )
        )
