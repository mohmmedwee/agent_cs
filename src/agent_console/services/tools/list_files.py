"""Tells the model which files the current user has uploaded."""

from agent_console.services.tools.context import ToolContext
from agent_console.services.tools.registry import ToolRegistry

__all__ = ["register"]

# Keep the tool result short so the next model turn can answer (ask which file)
# instead of drowning in a multi-KB duplicate dump.
_MAX_ROWS = 40


def register(registry: ToolRegistry, context: ToolContext) -> None:
    files = context.files
    user_id = context.user_id

    @registry.tool(
        name="list_uploaded_files",
        description=(
            "List the files the user has uploaded (newest first, unique names). "
            "Use when the user refers to a file without naming it exactly, then "
            "ask them which one in chat and stop."
        ),
        parameters={"type": "object", "properties": {}},
    )
    async def list_uploaded_files() -> str:
        rows = await files.list_for(user_id)
        if not rows:
            return "No files have been uploaded."

        # Newest first; keep first occurrence of each name so duplicates collapse.
        ordered = sorted(
            rows,
            key=lambda row: getattr(row, "uploaded_at", None)
            or getattr(row, "created_at", None)
            or 0,
            reverse=True,
        )
        seen: set[str] = set()
        unique = []
        for row in ordered:
            key = row.name.casefold()
            if key in seen:
                continue
            seen.add(key)
            unique.append(row)
            if len(unique) >= _MAX_ROWS:
                break

        def usage(row) -> str:
            if row.is_image:
                return "image"
            if row.is_text:
                return "text/docx"
            lower = row.name.lower()
            if lower.endswith((".docx", ".doc")):
                return "docx"
            if lower.endswith((".xlsx", ".xls", ".csv")):
                return "sheet"
            if lower.endswith((".pptx", ".ppt")):
                return "pptx"
            if lower.endswith((".png", ".jpg", ".jpeg", ".gif", ".webp")):
                return "image"
            return "file"

        lines = [
            f"{index}. {row.name} ({_fmt_size(row.size)}, {usage(row)})"
            for index, row in enumerate(unique, start=1)
        ]
        skipped = len(rows) - len(unique)
        if skipped > 0:
            lines.append(
                f"…plus {skipped} older duplicate/extra files not shown. "
                "Ask the user which numbered file to use."
            )
        else:
            lines.append("Ask the user which numbered file to use, then stop.")
        return "\n".join(lines)


def _fmt_size(size: int) -> str:
    if size < 1024:
        return f"{size} B"
    if size < 1024 * 1024:
        return f"{size / 1024:.1f} KB"
    return f"{size / (1024 * 1024):.1f} MB"
