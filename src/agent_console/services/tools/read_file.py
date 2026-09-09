"""Lets the model read the contents of an uploaded text file."""

from agent_console.repositories.files import UnknownFileError, UnreadableFileError
from agent_console.services.tools.context import ToolContext
from agent_console.services.tools.registry import ToolRegistry

__all__ = ["register"]


def register(registry: ToolRegistry, context: ToolContext) -> None:
    files = context.files
    max_chars = context.settings.max_file_chars

    @registry.tool(
        name="read_uploaded_file",
        description=(
            "Read the text of a file the user uploaded (plain text or .docx). "
            "Accepts the file name or its id. Long files come back in windows: "
            "if the result says characters remain, call again with the offset "
            "it gives you to read the rest."
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
    def read_uploaded_file(name: str, offset: int = 0) -> str:
        try:
            return files.read_text(name, max_chars=max_chars, offset=max(0, int(offset)))
        except UnknownFileError as exc:
            available = ", ".join(record.name for record in files.list()) or "none"
            return f"Error: {exc}. Uploaded files: {available}"
        except UnreadableFileError as exc:
            return f"Error: {exc}"
