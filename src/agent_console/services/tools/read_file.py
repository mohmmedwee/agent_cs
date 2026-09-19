"""Lets the model read the contents of a file the current user uploaded."""

from __future__ import annotations

from agent_console.repositories.files import UnknownFileError, UnreadableFileError
from agent_console.services.docx_blocks import assign_fresh_manifest, format_annotated
from agent_console.services.tools.context import ToolContext
from agent_console.services.tools.registry import ToolRegistry

__all__ = ["register"]


def _window(content: str, max_chars: int, offset: int) -> str:
    total = len(content)
    start = max(0, min(offset, total))
    window = content[start : start + max_chars]
    end = start + len(window)
    if start == 0 and end == total:
        return window
    remaining = (
        f"\n\n[{total - end} characters remain — call again with offset={end}]"
        if end < total
        else ""
    )
    return f"[characters {start}–{end} of {total}]\n\n{window}{remaining}"


def register(registry: ToolRegistry, context: ToolContext) -> None:
    files = context.files
    user_id = context.user_id
    max_chars = context.settings.max_file_chars

    @registry.tool(
        name="read_uploaded_file",
        description=(
            "Read the text of a file the user uploaded (plain text, .docx, or "
            ".pdf). DOCX lines are annotated as `[gN:p_#### h=…]` for edit_docx. "
            "PDFs include `--- Page N ---` markers. Accepts the file name or its "
            "id. Long files come back in windows: if the result says characters "
            "remain, call again with the offset it gives you to read the rest."
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
            row = await files.get(user_id, name)
            if row.name.lower().endswith(".docx"):
                data = await files.raw_bytes(user_id, str(row.id))
                # Fresh generation until edit_docx / convert persist manifests.
                manifest = assign_fresh_manifest(data, generation=1)
                return _window(
                    format_annotated(manifest),
                    max_chars,
                    max(0, int(offset)),
                )
            return await files.read_text(
                user_id, name, max_chars=max_chars, offset=max(0, int(offset))
            )
        except UnknownFileError as exc:
            available = ", ".join(row.name for row in await files.list_for(user_id))
            return f"Error: {exc}. Uploaded files: {available or 'none'}"
        except (UnreadableFileError, ValueError) as exc:
            return f"Error: {exc}"
