"""Registry mapping tool names to callables and their JSON schemas."""

import asyncio
import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from agent_console.models.chat import ToolSchema

__all__ = ["Tool", "ToolRegistry"]


@dataclass(frozen=True, slots=True)
class Tool:
    name: str
    fn: Callable[..., Any]
    schema: ToolSchema


class ToolRegistry:
    """Holds the tools an agent may call.

    Sync callables are pushed to a thread so they never block the event loop.
    Exceptions are returned to the model as text rather than raised, which lets
    it retry with corrected arguments instead of failing the whole request.
    """

    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def tool(
        self, *, name: str, description: str, parameters: dict[str, Any]
    ) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        """Decorator registering a callable as a tool."""

        def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
            if name in self._tools:
                raise ValueError(f"tool {name!r} is already registered")
            self._tools[name] = Tool(
                name=name,
                fn=fn,
                schema=ToolSchema(
                    function={
                        "name": name,
                        "description": description,
                        "parameters": parameters,
                    }
                ),
            )
            return fn

        return decorator

    @property
    def names(self) -> set[str]:
        return set(self._tools)

    @property
    def schemas(self) -> list[ToolSchema]:
        return [tool.schema for tool in self._tools.values()]

    async def invoke(self, name: str, raw_arguments: str) -> str:
        """Run a tool. Every failure path returns a string for the model to read."""
        tool = self._tools.get(name)
        if tool is None:
            return f"Error: no tool named {name}."
        try:
            arguments = json.loads(raw_arguments or "{}")
        except json.JSONDecodeError:
            return f"Error: arguments were not valid JSON: {raw_arguments!r}"
        try:
            if asyncio.iscoroutinefunction(tool.fn):
                result = await tool.fn(**arguments)
            else:
                result = await asyncio.to_thread(tool.fn, **arguments)
            return str(result)
        except Exception as exc:
            return f"Error: {type(exc).__name__}: {exc}"
