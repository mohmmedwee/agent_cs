"""Request and response schemas for the chat endpoint."""

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

__all__ = ["ChatRequest", "Effort", "ModelInfo", "ModelListResponse"]

# Maps onto the upstream `reasoning_effort` parameter, which measurably shortens
# this model's thinking: "minimal" cut it by about two thirds against baseline.
Effort = Literal["minimal", "low", "medium", "high"]


class ChatRequest(BaseModel):
    """One user turn against a stored conversation.

    Prior turns are loaded server-side from the conversation, so the client
    sends only what is new.
    """

    conversation_id: UUID
    message: str = Field(min_length=1)
    model: str | None = None
    effort: Effort | None = None


class ModelInfo(BaseModel):
    id: str
    loaded: bool = False


class ModelListResponse(BaseModel):
    models: list[ModelInfo]
    current: str | None = None
