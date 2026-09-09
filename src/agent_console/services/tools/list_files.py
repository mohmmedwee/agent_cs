"""Lets the model discover which files the user has uploaded."""

from agent_console.services.tools.context import ToolContext
from agent_console.services.tools.registry import ToolRegistry

__all__ = ["register"]


def register(registry: ToolRegistry, context: ToolContext) -> None:
    files = context.files

    @registry.tool(
        name="list_uploaded_files",
        description=(
            "List the files the user has uploaded in this session, with their sizes. "
            "Call this when the user refers to a file, an attachment, or a document."
        ),
        parameters={"type": "object", "properties": {}},
    )
    def list_uploaded_files() -> str:
        records = files.list()
        if not records:
            return "No files have been uploaded."
        return "\n".join(
            f"{record.name} — {record.size} bytes"
            + ("" if record.is_text else " (binary, contents not readable as text)")
            for record in records
        )
