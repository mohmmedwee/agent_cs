"""Let the agent produce a file the user can download.

Without this the agent can only read; anything it writes has to be copied out
of the chat by hand. Written files land in the same store as uploads, so they
appear in the file list and are downloadable.
"""

from agent_console.repositories.files import FileTooLargeError
from agent_console.services.tools.context import ToolContext
from agent_console.services.tools.registry import ToolRegistry

__all__ = ["register"]


def register(registry: ToolRegistry, context: ToolContext) -> None:
    files = context.files

    @registry.tool(
        name="write_file",
        description=(
            "Save text as a file the user can download. Use when the user asks "
            "for a document, report, summary, or code file as an artifact rather "
            "than as chat text. Returns the download link."
        ),
        parameters={
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "File name including extension, e.g. summary.md.",
                },
                "content": {
                    "type": "string",
                    "description": "The full text to write.",
                },
            },
            "required": ["name", "content"],
        },
    )
    def write_file(name: str, content: str) -> str:
        try:
            record = files.save(
                name=name, data=content.encode("utf-8"), content_type="text/plain"
            )
        except FileTooLargeError as exc:
            return f"Error: {exc}"
        return (
            f"Wrote {record.name} ({record.size} bytes). "
            f"Download: /api/files/{record.id}/download"
        )
