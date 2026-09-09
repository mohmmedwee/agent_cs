"""Request and response shapes for user memory."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

__all__ = [
    "MemoryCreateRequest",
    "MemoryListResponse",
    "MemoryResponse",
    "MemoryUpdateRequest",
]


class MemoryCreateRequest(BaseModel):
    content: str = Field(min_length=1, max_length=2000)


class MemoryUpdateRequest(BaseModel):
    content: str = Field(min_length=1, max_length=2000)


class MemoryResponse(BaseModel):
    id: UUID
    content: str
    source: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class MemoryListResponse(BaseModel):
    memories: list[MemoryResponse]
