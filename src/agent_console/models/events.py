"""Typed events emitted by the agent loop.

The transport carries these rather than raw tokens, which is what lets the UI
render a tool call as its own block while text streams around it.
"""

from typing import Annotated, Literal

from pydantic import BaseModel, Field

__all__ = [
    "AgentEvent",
    "DoneEvent",
    "ErrorEvent",
    "ReasoningDeltaEvent",
    "TextDeltaEvent",
    "ToolCallEvent",
    "ToolResultEvent",
]


class TextDeltaEvent(BaseModel):
    type: Literal["text_delta"] = "text_delta"
    text: str


class ReasoningDeltaEvent(BaseModel):
    """A reasoning model's private thinking.

    Kept separate from `text_delta` so the UI can show progress without mixing
    scratch work into the answer. It is never fed back to the model.
    """

    type: Literal["reasoning_delta"] = "reasoning_delta"
    text: str


class ToolCallEvent(BaseModel):
    type: Literal["tool_call"] = "tool_call"
    id: str
    name: str
    arguments: str


class ToolResultEvent(BaseModel):
    type: Literal["tool_result"] = "tool_result"
    id: str
    name: str
    result: str


class ErrorEvent(BaseModel):
    type: Literal["error"] = "error"
    message: str


class DoneEvent(BaseModel):
    type: Literal["done"] = "done"
    steps: int


AgentEvent = Annotated[
    TextDeltaEvent
    | ReasoningDeltaEvent
    | ToolCallEvent
    | ToolResultEvent
    | ErrorEvent
    | DoneEvent,
    Field(discriminator="type"),
]
