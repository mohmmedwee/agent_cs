"""Wire types for the OpenAI-compatible chat completions API."""

from typing import Any, Literal

from pydantic import BaseModel, Field

__all__ = ["FunctionCall", "ToolCall", "ToolSchema", "build_tool_message"]


class FunctionCall(BaseModel):
    name: str = ""
    arguments: str = ""


class ToolCall(BaseModel):
    id: str = ""
    type: Literal["function"] = "function"
    function: FunctionCall = Field(default_factory=FunctionCall)


class ToolSchema(BaseModel):
    """JSON-schema description of a tool, as the endpoint expects it."""

    type: Literal["function"] = "function"
    function: dict[str, Any]


def build_tool_message(call_id: str, name: str, content: str) -> dict[str, Any]:
    """The `role: tool` turn that carries a result back to the model."""
    return {"role": "tool", "tool_call_id": call_id, "name": name, "content": content}
