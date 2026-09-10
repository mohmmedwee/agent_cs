"""Lets the model read the contents of a file the current user uploaded."""

from agent_console.repositories.files import UnknownFileError, UnreadableFileError
from agent_console.services.tools.context import ToolContext
from agent_console.services.tools.registry import ToolRegistry

__all__ = ["register"]


def register(registry: ToolRegistry, context: ToolContext) -> None:
    files = context.files
    user_id = context.user_id
    max_chars = context.settings.max_file_chars

    @registry.tool(
        name="read_uploaded_file",
        description=(
            "Read the text of a file the user uploaded (plain text, .docx, or "
            ".pdf). PDFs include `--- Page N ---` markers. Accepts the file "
            "name or its id. Long files come back in windows: if the result "
            "says characters remain, call again with the offset it gives you "
            "to read the rest."
        ),
        parameters={
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "The file's name, e.g. report.md, or its id.",
                },
                "offset": {
                    "type": "integer",
                    "description": "Character position to start from. Defaults to 0.",
                },
            },
            "required": ["name"],
        },
    )
    async def read_uploaded_file(name: str, offset: int = 0) -> str:
        try:
            return await files.read_text(
                user_id, name, max_chars=max_chars, offset=max(0, int(offset))
            )
        except UnknownFileError as exc:
            available = ", ".join(row.name for row in await files.list_for(user_id))
            return f"Error: {exc}. Uploaded files: {available or 'none'}"
        except UnreadableFileError as exc:
            return f"Error: {exc}"
