"""Request and response schemas for the chat endpoint."""

from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, BeforeValidator, Field

__all__ = [
    "ChatRequest",
    "Effort",
    "ModelInfo",
    "ModelListResponse",
    "ToolApprovalRequest",
]

# Qwen3.8 accepts only low / medium / xhigh (not "high"). "minimal" is our
# app-level "instant" preset: low thinking + a short tool-step budget.
_EffortValue = Literal["minimal", "low", "medium", "xhigh"]


def _coerce_effort(value: object) -> object:
    if not isinstance(value, str):
        return value
    key = value.strip().lower().replace("x-high", "xhigh")
    if key == "high":
        return "xhigh"
    return key


Effort = Annotated[_EffortValue, BeforeValidator(_coerce_effort)]


class ChatRequest(BaseModel):
    """One user turn against a stored conversation.

    Prior turns are loaded server-side from the conversation, so the client
    sends only what is new.
    """

    conversation_id: UUID
    message: str = Field(min_length=1)
    model: str | None = None
    effort: Effort | None = None
    # Tools the user has set to "always allow" — skip HITL for these names.
    auto_approve_tools: list[str] = Field(default_factory=list)
    # Composer toggles: steer tool/skill use for this turn.
    web_search: bool = False
    research: bool = False
    skill: str | None = Field(default=None, max_length=64)


class ToolApprovalRequest(BaseModel):
    """Allow or deny a paused tool call while the chat stream is still open."""

    conversation_id: UUID
    call_id: str = Field(min_length=1)
    allowed: bool


class ModelInfo(BaseModel):
    id: str
    loaded: bool = False


class ModelListResponse(BaseModel):
    models: list[ModelInfo]
    current: str | None = None
