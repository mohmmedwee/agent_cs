"""Tool registry and the tools themselves — one module per tool.

To add a tool: drop a module in this package that defines

    def register(registry: ToolRegistry, context: ToolContext) -> None

and it is picked up automatically. Modules without a `register` function
(`registry`, `context`) are infrastructure and are skipped.
"""

import importlib
import pkgutil
from types import ModuleType

from agent_console.services.tools.context import ToolContext
from agent_console.services.tools.registry import Tool, ToolRegistry

__all__ = ["Tool", "ToolContext", "ToolRegistry", "build_registry", "discover_tool_modules"]


def discover_tool_modules() -> list[ModuleType]:
    """Every module in this package that exposes a `register` function."""
    modules = []
    for info in pkgutil.iter_modules(__path__):
        if info.name.startswith("_"):
            continue
        module = importlib.import_module(f"{__name__}.{info.name}")
        if callable(getattr(module, "register", None)):
            modules.append(module)
    return modules


def build_registry(context: ToolContext) -> ToolRegistry:
    """Construct a registry with every discovered tool registered on it."""
    registry = ToolRegistry()
    for module in discover_tool_modules():
        module.register(registry, context)
    return registry
