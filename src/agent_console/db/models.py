"""Database tables.

Every row that belongs to a person carries `user_id` and cascades from it, so
deleting a user removes their data rather than orphaning it.
"""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from agent_console.db.base import Base, timestamp_column, utcnow

__all__ = [
    "Conversation",
    "Message",
    "StoredFileRow",
    "User",
    "UserMemory",
    "UserSkill",
]


def _pk() -> Mapped[UUID]:
    return mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid4)


class User(Base):
    __tablename__ = "users"

    id: Mapped[UUID] = _pk()
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(120))
    password_hash: Mapped[str] = mapped_column(Text)
    is_admin: Mapped[bool] = mapped_column(default=False)
    is_active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = timestamp_column()

    conversations: Mapped[list["Conversation"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    files: Mapped[list["StoredFileRow"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    memories: Mapped[list["UserMemory"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    skills: Mapped[list["UserSkill"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[UUID] = _pk()
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    title: Mapped[str] = mapped_column(String(200), default="New chat")
    # When set, this chat was forked from another. All siblings share the root
    # as parent_id so the branch switcher stays a flat family list.
    parent_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("conversations.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    # How many leading messages were copied from the parent at fork time.
    branched_at_position: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Rolling summary of older turns so long chats fit the model window.
    # `summarized_count` is how many leading transcript messages are covered.
    context_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    summarized_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = timestamp_column()
    updated_at: Mapped[datetime] = timestamp_column(onupdate=utcnow)

    user: Mapped[User] = relationship(back_populates="conversations")
    messages: Mapped[list["Message"]] = relationship(
        back_populates="conversation",
        cascade="all, delete-orphan",
        order_by="Message.position",
    )

    # The sidebar always asks for one user's conversations, newest first.
    __table_args__ = (Index("ix_conversations_user_updated", "user_id", "updated_at"),)


class Message(Base):
    """One turn.

    `blocks` holds the rendered structure — tool calls, reasoning, text — so a
    reloaded conversation shows what the loop did, not just the prose. `content`
    holds the plain text that is replayed to the model.
    """

    __tablename__ = "messages"

    id: Mapped[UUID] = _pk()
    conversation_id: Mapped[UUID] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), index=True
    )
    position: Mapped[int] = mapped_column()
    role: Mapped[str] = mapped_column(String(16))
    content: Mapped[str] = mapped_column(Text, default="")
    blocks: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = timestamp_column()

    conversation: Mapped[Conversation] = relationship(back_populates="messages")

    __table_args__ = (
        UniqueConstraint("conversation_id", "position", name="uq_message_position"),
    )


class StoredFileRow(Base):
    """Metadata for an upload. The bytes stay on disk under `storage_key`."""

    __tablename__ = "files"
    __table_args__ = (
        # Linear chains: at most one child per parent. Multiple NULL parents
        # (roots) are allowed — Postgres UNIQUE permits several NULLs.
        UniqueConstraint("parent_id", name="uq_files_parent_id"),
    )

    id: Mapped[UUID] = _pk()
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(400))
    storage_key: Mapped[str] = mapped_column(String(64), unique=True)
    size: Mapped[int] = mapped_column()
    content_type: Mapped[str | None] = mapped_column(String(200), nullable=True)
    # What the agent can do with it: read as text, look at with the vision
    # model, or neither. Both are stored rather than derived on read so the
    # file list does not have to open every file.
    is_text: Mapped[bool] = mapped_column(default=False)
    is_image: Mapped[bool] = mapped_column(default=False, server_default="false")
    # Linear version chain. Roots have parent_id NULL and root_id = id.
    # derived_from records content provenance (e.g. markdown source) without
    # being the parent link — so convert rebuilds can parent the tip.
    root_id: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("files.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    parent_id: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("files.id", ondelete="SET NULL"),
        nullable=True,
    )
    derived_from: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("files.id", ondelete="SET NULL"),
        nullable=True,
    )
    version: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    uploaded_at: Mapped[datetime] = timestamp_column()

    user: Mapped[User] = relationship(back_populates="files")


class UserMemory(Base):
    """A durable fact or preference about the user, used across conversations."""

    __tablename__ = "user_memories"

    id: Mapped[UUID] = _pk()
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    content: Mapped[str] = mapped_column(Text)
    # "agent" when remember tool wrote it; "user" when edited in the Memory UI.
    source: Mapped[str] = mapped_column(String(16), default="agent")
    created_at: Mapped[datetime] = timestamp_column()
    updated_at: Mapped[datetime] = timestamp_column(onupdate=utcnow)

    user: Mapped[User] = relationship(back_populates="memories")

    __table_args__ = (
        Index("ix_user_memories_user_updated", "user_id", "updated_at"),
    )


class UserSkill(Base):
    """A user-authored skill (Markdown body) loaded on demand via read_skill."""

    __tablename__ = "user_skills"

    id: Mapped[UUID] = _pk()
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(64))
    description: Mapped[str] = mapped_column(String(500))
    body: Mapped[str] = mapped_column(Text)
    enabled: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = timestamp_column()
    updated_at: Mapped[datetime] = timestamp_column(onupdate=utcnow)

    user: Mapped[User] = relationship(back_populates="skills")

    __table_args__ = (
        UniqueConstraint("user_id", "name", name="uq_user_skills_user_name"),
        Index("ix_user_skills_user_updated", "user_id", "updated_at"),
    )
