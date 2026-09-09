"""Durable per-user facts and preferences for the agent."""

from uuid import UUID

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from agent_console.db.models import UserMemory

__all__ = [
    "MemoryRepository",
    "MemoryLimitError",
    "UnknownMemoryError",
]


class UnknownMemoryError(LookupError):
    """No memory with that id belongs to this user."""


class MemoryLimitError(ValueError):
    """Too many memories or content that is too long."""


class MemoryRepository:
    def __init__(
        self,
        session: AsyncSession,
        *,
        max_items: int = 50,
        max_chars: int = 400,
    ) -> None:
        self._session = session
        self._max_items = max_items
        self._max_chars = max_chars

    async def list_for(self, user_id: UUID) -> list[UserMemory]:
        result = await self._session.execute(
            select(UserMemory)
            .where(UserMemory.user_id == user_id)
            .order_by(UserMemory.updated_at.desc())
        )
        return list(result.scalars())

    async def get(self, user_id: UUID, memory_id: UUID) -> UserMemory:
        result = await self._session.execute(
            select(UserMemory).where(
                UserMemory.id == memory_id,
                UserMemory.user_id == user_id,
            )
        )
        row = result.scalar_one_or_none()
        if row is None:
            raise UnknownMemoryError(f"no memory {memory_id}")
        return row

    async def count_for(self, user_id: UUID) -> int:
        result = await self._session.execute(
            select(func.count())
            .select_from(UserMemory)
            .where(UserMemory.user_id == user_id)
        )
        return int(result.scalar_one())

    def _clean(self, content: str) -> str:
        text = " ".join(content.strip().split())
        if not text:
            raise MemoryLimitError("memory content cannot be empty")
        if len(text) > self._max_chars:
            raise MemoryLimitError(
                f"memory is {len(text)} characters; limit is {self._max_chars}"
            )
        return text

    async def add(
        self, user_id: UUID, content: str, *, source: str = "agent"
    ) -> UserMemory:
        text = self._clean(content)
        if await self.count_for(user_id) >= self._max_items:
            raise MemoryLimitError(
                f"already at the limit of {self._max_items} memories — "
                "forget something first"
            )
        row = UserMemory(user_id=user_id, content=text, source=source)
        self._session.add(row)
        await self._session.flush()
        return row

    async def update(
        self, user_id: UUID, memory_id: UUID, content: str
    ) -> UserMemory:
        row = await self.get(user_id, memory_id)
        row.content = self._clean(content)
        row.source = "user"
        await self._session.flush()
        return row

    async def delete(self, user_id: UUID, memory_id: UUID) -> None:
        row = await self.get(user_id, memory_id)
        await self._session.delete(row)
        await self._session.flush()

    async def delete_matching(self, user_id: UUID, query: str) -> list[str]:
        """Remove memories whose content contains `query` (case-insensitive)."""
        needle = query.strip().lower()
        if not needle:
            raise MemoryLimitError("forget query cannot be empty")
        rows = await self.list_for(user_id)
        removed: list[str] = []
        for row in rows:
            if needle in row.content.lower():
                removed.append(row.content)
                await self._session.delete(row)
        await self._session.flush()
        return removed

    async def prompt_block(self, user_id: UUID) -> str:
        """Markdown section injected into the system prompt, or empty."""
        rows = await self.list_for(user_id)
        if not rows:
            return ""
        # Oldest-first so stable facts feel chronological when the model reads.
        lines = [f"- {row.content}" for row in reversed(rows)]
        return (
            "## About this user\n\n"
            "Durable notes from prior chats. Use them. Do not invent extras. "
            "Update with `remember` / `forget` when the user corrects something.\n\n"
            + "\n".join(lines)
        )
