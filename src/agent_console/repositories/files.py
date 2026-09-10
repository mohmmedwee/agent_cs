"""Uploaded files: metadata in Postgres, bytes on disk.

Bytes stay on the filesystem because streaming them through the database buys
nothing here. The row is the source of truth for what exists and who owns it,
so a file with no row is invisible even if it is still on disk.

Every method is scoped by `user_id`; one user can never reach another's file.
"""

import unicodedata
from pathlib import Path
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agent_console.db.models import StoredFileRow
from agent_console.repositories.extraction import extract_text
from agent_console.repositories.images import image_media_type

__all__ = [
    "FileRepository",
    "FileTooLargeError",
    "UnknownFileError",
    "UnreadableFileError",
]


class UnknownFileError(LookupError):
    """No file matches the given id or name for this user."""


class FileTooLargeError(ValueError):
    """The upload exceeded the configured size limit."""


class UnreadableFileError(ValueError):
    """The file is stored but we have no way to read it as text."""


def _safe_name(name: str) -> str:
    """Strip any directory component so an upload cannot escape the store."""
    cleaned = unicodedata.normalize("NFC", name).replace("\\", "/")
    return Path(cleaned).name or "unnamed"


class FileRepository:
    def __init__(self, session: AsyncSession, directory: Path, max_bytes: int) -> None:
        self._session = session
        self._directory = directory
        self._max_bytes = max_bytes
        self._directory.mkdir(parents=True, exist_ok=True)

    def _path(self, storage_key: str) -> Path:
        return self._directory / storage_key

    async def save(
        self, user_id: UUID, name: str, data: bytes, content_type: str | None = None
    ) -> StoredFileRow:
        if len(data) > self._max_bytes:
            raise FileTooLargeError(
                f"{name} is {len(data)} bytes; the limit is {self._max_bytes}"
            )

        safe = _safe_name(name)
        storage_key = uuid4().hex
        self._path(storage_key).write_bytes(data)

        row = StoredFileRow(
            user_id=user_id,
            name=safe,
            storage_key=storage_key,
            size=len(data),
            content_type=content_type,
            # "Can the agent read this?", not "are these bytes UTF-8?" — a .docx
            # is binary but perfectly readable once unpacked.
            is_text=extract_text(data, safe) is not None,
            # Detected from the header, not the extension, because that is what
            # the vision model will actually receive.
            is_image=image_media_type(data) is not None,
        )
        self._session.add(row)
        await self._session.flush()
        return row

    async def list_for(self, user_id: UUID) -> list[StoredFileRow]:
        result = await self._session.execute(
            select(StoredFileRow)
            .where(StoredFileRow.user_id == user_id)
            .order_by(StoredFileRow.uploaded_at)
        )
        return list(result.scalars())

    async def get(self, user_id: UUID, ref: str) -> StoredFileRow:
        """Look up by id, then by exact name — the model tends to use the name."""
        try:
            row = await self._session.get(StoredFileRow, UUID(ref))
            if row is not None and row.user_id == user_id:
                return row
        except (ValueError, AttributeError):
            pass

        result = await self._session.execute(
            select(StoredFileRow).where(
                StoredFileRow.user_id == user_id, StoredFileRow.name == ref
            )
        )
        row = result.scalars().first()
        if row is None:
            raise UnknownFileError(f"no uploaded file matches {ref!r}")
        return row

    async def raw_bytes(self, user_id: UUID, ref: str) -> bytes:
        row = await self.get(user_id, ref)
        return self._path(row.storage_key).read_bytes()

    async def delete(self, user_id: UUID, ref: str) -> None:
        row = await self.get(user_id, ref)
        self._path(row.storage_key).unlink(missing_ok=True)
        await self._session.delete(row)
        await self._session.flush()

    async def text(self, user_id: UUID, ref: str) -> str:
        row = await self.get(user_id, ref)
        content = extract_text(self._path(row.storage_key).read_bytes(), row.name)
        if content is None:
            raise UnreadableFileError(
                f"{row.name} is not a format this server can read as text "
                "(plain text, .docx, and .pdf are supported)"
            )
        # Older PDF rows may have been saved before extraction existed.
        if not row.is_text:
            row.is_text = True
            await self._session.flush()
        return content

    async def read_text(
        self, user_id: UUID, ref: str, max_chars: int, offset: int = 0
    ) -> str:
        """A window of the file's text.

        The window is explicit so a document longer than `max_chars` is paged
        through rather than silently cut off at the first screenful.
        """
        content = await self.text(user_id, ref)
        total = len(content)
        start = max(0, min(offset, total))
        window = content[start : start + max_chars]
        end = start + len(window)

        if start == 0 and end == total:
            return window

        remaining = (
            f"\n\n[{total - end} characters remain — call again with offset={end}]"
            if end < total
            else ""
        )
        return f"[characters {start}–{end} of {total}]\n\n{window}{remaining}"
