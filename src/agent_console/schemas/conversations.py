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
]


class CreateConversationRequest(BaseModel):
    title: str = Field(default="New chat", max_length=200)


class RenameConversationRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200)


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


class ConversationListResponse(BaseModel):
    conversations: list[ConversationSummary]
