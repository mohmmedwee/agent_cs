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
    "ToolApprovalEvent",
    "ToolCallDeltaEvent",
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


class ToolCallDeltaEvent(BaseModel):
    """Progress while a tool call's arguments are still being generated.

    Long calls (a multi-page `write_file`) can take minutes with no text
    deltas. The name and argument length are enough for the UI to show what is
    happening without flooding the stream with the document itself.
    """

    type: Literal["tool_call_delta"] = "tool_call_delta"
    index: int
    id: str = ""
    name: str = ""
    arguments_chars: int = 0


class ToolCallEvent(BaseModel):
    type: Literal["tool_call"] = "tool_call"
    id: str
    name: str
    arguments: str


class ToolApprovalEvent(BaseModel):
    """Human-in-the-loop gate: the loop is paused until allow/deny.

    Emitted after `tool_call` and before `tool_result` for tools listed in
    `approval_required_tools`. For `edit_docx`, `approval_card` is a
    server-built plaintext diff the Composer renders as-is.
    """

    type: Literal["tool_approval"] = "tool_approval"
    id: str
    name: str
    arguments: str
    approval_card: dict | None = None


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
    | ToolCallDeltaEvent
    | ToolCallEvent
    | ToolApprovalEvent
    | ToolResultEvent
    | ErrorEvent
    | DoneEvent,
    Field(discriminator="type"),
]
