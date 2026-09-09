"""Request and response schemas for the chat endpoint."""

from typing import Any

from pydantic import BaseModel, Field

__all__ = ["ChatRequest"]


class ChatRequest(BaseModel):
    """Conversation state is replayed by the client on every request.

    Move this server-side, keyed by conversation id, before adding multi-user
    support, prompt caching, or context trimming.
    """

    messages: list[dict[str, Any]] = Field(min_length=1)
