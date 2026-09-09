"""Tells the model which files the current user has uploaded."""

from agent_console.services.tools.context import ToolContext
from agent_console.services.tools.registry import ToolRegistry

__all__ = ["register"]


def register(registry: ToolRegistry, context: ToolContext) -> None:
    files = context.files
    user_id = context.user_id

    @registry.tool(
        name="list_uploaded_files",
        description=(
            "List the files the user has uploaded, with their sizes and how each "
            "can be used. Use when the user refers to a file without naming it "
            "exactly."
        ),
        parameters={"type": "object", "properties": {}},
    )
    async def list_uploaded_files() -> str:
        rows = await files.list_for(user_id)
        if not rows:
            return "No files have been uploaded."

        # Say which tool applies, so the model does not try to read an image as
        # text and conclude the file is broken.
        def usage(row) -> str:
            if row.is_image:
                return "image — use view_image"
            if row.is_text:
                return "text — use read_uploaded_file"
            return "cannot be read"

        return "\n".join(
            f"{row.name} ({row.size} bytes) — {usage(row)}" for row in rows
        )
