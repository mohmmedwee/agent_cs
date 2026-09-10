"""Let the agent produce a file the user can download.

Without this the agent can only read; anything it writes has to be copied out
of the chat by hand. Written files land in the same store as uploads, so they
appear in the file list and are downloadable.
"""

from pathlib import Path

from agent_console.repositories.documents import DOCX_MEDIA_TYPE, build_docx
from agent_console.repositories.files import FileTooLargeError
from agent_console.repositories.spreadsheets import XLSX_MEDIA_TYPE, build_xlsx
from agent_console.services.tools.context import ToolContext
from agent_console.services.tools.registry import ToolRegistry

__all__ = ["register"]

# Extensions whose format we cannot actually produce. Writing text under one of
# these names yields a file the user cannot open, so refuse and say so instead.
_UNSUPPORTED = {".pdf", ".doc", ".xls", ".ppt", ".pptx", ".odt", ".rtf"}

_TEXT_TYPES = {
    ".md": "text/markdown",
    ".markdown": "text/markdown",
    ".csv": "text/csv",
    ".json": "application/json",
    ".html": "text/html",
    ".xml": "application/xml",
}


def register(registry: ToolRegistry, context: ToolContext) -> None:
    files = context.files
    user_id = context.user_id

    @registry.tool(
        name="write_file",
        description=(
            "Save text as a file the user can download. Use when the user asks "
            "to create or export a document, report, summary, spreadsheet, or "
            "code file. If they describe the columns or topic but give no rows, "
            "invent a small realistic sample and write it — do not ask for data "
            "first. Write content as Markdown: .docx becomes a Word document; "
            ".xlsx turns Markdown tables (or CSV) into a real Excel workbook. "
            "Other extensions are plain text. PDF and older Office formats "
            "cannot be produced. Returns the download link."
        ),
        parameters={
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "File name including extension, e.g. report.docx.",
                },
                "content": {
                    "type": "string",
                    "description": "The full text to write, as Markdown.",
                },
            },
            "required": ["name", "content"],
        },
    )
    async def write_file(name: str, content: str) -> str:
        suffix = Path(name).suffix.lower()
        if suffix in _UNSUPPORTED:
            return (
                f"Error: this server cannot build {suffix} files. Offer the user "
                "a .docx, .xlsx, or .md instead, then call this tool again."
            )

        if suffix == ".docx":
            data, content_type = build_docx(content), DOCX_MEDIA_TYPE
        elif suffix == ".xlsx":
            data, content_type = build_xlsx(content), XLSX_MEDIA_TYPE
        else:
            data = content.encode("utf-8")
            content_type = _TEXT_TYPES.get(suffix, "text/plain")

        try:
            row = await files.save(
                user_id, name=name, data=data, content_type=content_type
            )
        except FileTooLargeError as exc:
            return f"Error: {exc}"
        return (
            f"Wrote {row.name} ({row.size} bytes). "
            f"Download: /api/files/{row.id}/download"
        )
