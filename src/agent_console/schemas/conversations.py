"""Request and response shapes for conversations."""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

__all__ = [
    "ConversationDetail",
    "ConversationListResponse",
    "ConversationSummary",
    "CreateConversationRequest",
    "MessageResponse",
    "RenameConversationRequest",
    "RewindConversationRequest",
]


class CreateConversationRequest(BaseModel):
    title: str = Field(default="New chat", max_length=200)


class RenameConversationRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200)


class RewindConversationRequest(BaseModel):
    """Keep the first N messages; delete everything after (for edit & regenerate)."""

    keep: int = Field(ge=0)


class MessageResponse(BaseModel):
    id: UUID
    role: str
    content: str
    blocks: list[dict[str, Any]] | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class ConversationSummary(BaseModel):
    id: UUID
    title: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ConversationDetail(ConversationSummary):
    messages: list[MessageResponse] = []
    # True when older turns were folded for the model; UI still shows everything.
    context_compressed: bool = False
    context_summary: str | None = None
    summarized_count: int = 0

    @classmethod
    def from_row(cls, row: Any) -> "ConversationDetail":
        summary = (row.context_summary or "").strip() or None
        return cls(
            id=row.id,
            title=row.title,
            created_at=row.created_at,
            updated_at=row.updated_at,
            messages=[MessageResponse.model_validate(m) for m in row.messages],
            context_compressed=bool(summary),
            context_summary=summary,
            summarized_count=int(row.summarized_count or 0),
        )


class ConversationListResponse(BaseModel):
    conversations: list[ConversationSummary]
