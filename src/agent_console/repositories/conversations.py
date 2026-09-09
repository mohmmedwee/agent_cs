"""Conversations and their messages, always scoped to one user.

Every method takes `user_id` and filters on it. Ownership is enforced here
rather than in the routes so a new endpoint cannot forget to check it.
"""

from typing import Any
from uuid import UUID

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from agent_console.db.base import utcnow
from agent_console.db.models import Conversation, Message

__all__ = ["ConversationRepository", "UnknownConversationError"]

_TITLE_LIMIT = 60


class UnknownConversationError(LookupError):
    """No conversation with that id belongs to this user."""


def title_from(text: str) -> str:
    line = text.strip().split("\n", 1)[0]
    if len(line) > _TITLE_LIMIT:
        return f"{line[:_TITLE_LIMIT]}…"
    return line or "New chat"


class ConversationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, user_id: UUID, title: str = "New chat") -> Conversation:
        conversation = Conversation(user_id=user_id, title=title)
        self._session.add(conversation)
        await self._session.flush()
        return conversation

    async def list_for(self, user_id: UUID) -> list[Conversation]:
        result = await self._session.execute(
            select(Conversation)
            .where(Conversation.user_id == user_id)
            .order_by(Conversation.updated_at.desc())
        )
        return list(result.scalars())

    async def get(self, user_id: UUID, conversation_id: UUID) -> Conversation:
        result = await self._session.execute(
            select(Conversation)
            .where(
                Conversation.id == conversation_id,
                Conversation.user_id == user_id,
            )
            .options(selectinload(Conversation.messages))
        )
        conversation = result.scalar_one_or_none()
        if conversation is None:
            raise UnknownConversationError(f"no conversation {conversation_id}")
        return conversation

    async def rename(self, user_id: UUID, conversation_id: UUID, title: str) -> Conversation:
        conversation = await self.get(user_id, conversation_id)
        conversation.title = title.strip()[:200] or "New chat"
        await self._session.flush()
        return conversation

    async def delete(self, user_id: UUID, conversation_id: UUID) -> None:
        result = await self._session.execute(
            delete(Conversation).where(
                Conversation.id == conversation_id,
                Conversation.user_id == user_id,
            )
        )
        if result.rowcount == 0:
            raise UnknownConversationError(f"no conversation {conversation_id}")

    async def _next_position(self, conversation_id: UUID) -> int:
        result = await self._session.execute(
            select(func.coalesce(func.max(Message.position), -1)).where(
                Message.conversation_id == conversation_id
            )
        )
        return int(result.scalar_one()) + 1

    async def truncate_from(
        self, user_id: UUID, conversation_id: UUID, keep: int
    ) -> Conversation:
        """Drop messages from `keep` onward so the user can edit and regenerate.

        `keep` is a count of leading messages to retain (0 = clear the thread).
        """
        conversation = await self.get(user_id, conversation_id)
        if keep < 0:
            keep = 0
        await self._session.execute(
            delete(Message).where(
                Message.conversation_id == conversation.id,
                Message.position >= keep,
            )
        )
        # Rewind invalidates any summary that covered deleted or shifted turns.
        conversation.context_summary = None
        conversation.summarized_count = 0
        conversation.updated_at = utcnow()
        await self._session.flush()
        # Reload so callers see the trimmed message list.
        return await self.get(user_id, conversation_id)

    async def append(
        self,
        user_id: UUID,
        conversation_id: UUID,
        role: str,
        content: str,
        blocks: list[dict[str, Any]] | None = None,
    ) -> Message:
        conversation = await self.get(user_id, conversation_id)

        message = Message(
            conversation_id=conversation.id,
            position=await self._next_position(conversation.id),
            role=role,
            content=content,
            blocks=blocks,
        )
        self._session.add(message)

        # First user message names the conversation.
        if role == "user" and conversation.title in ("", "New chat"):
            conversation.title = title_from(content)
        conversation.updated_at = utcnow()

        await self._session.flush()
        return message

    async def history(self, user_id: UUID, conversation_id: UUID) -> list[dict[str, str]]:
        """Prior turns as plain chat messages, for replay to the model."""
        conversation = await self.get(user_id, conversation_id)
        return [
            {"role": message.role, "content": message.content}
            for message in conversation.messages
            if message.content
        ]
