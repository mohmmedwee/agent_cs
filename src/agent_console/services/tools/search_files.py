"""Find a term across uploaded documents without reading them whole.

Reading a long document into the conversation costs prefill on every later
step. Searching first lets the model locate the relevant passage and spend its
context on that instead.
"""

from __future__ import annotations

import re

from agent_console.repositories.extraction import page_at_offset
from agent_console.repositories.files import UnknownFileError, UnreadableFileError
from agent_console.services.tools.context import ToolContext
from agent_console.services.tools.registry import ToolRegistry

__all__ = ["register", "find_ci"]

_CONTEXT_CHARS = 160
_MAX_HITS_PER_FILE = 5


def find_ci(haystack: str, needle: str, *, start: int = 0) -> tuple[int, int] | None:
    """Case-insensitive literal find; spans refer to the original haystack.

    Avoids `haystack.lower()`, which can change string length for some Unicode
    characters and drift character offsets.
    """
    if not needle:
        return None
    match = re.compile(re.escape(needle), re.IGNORECASE).search(haystack, start)
    if match is None:
        return None
    return match.start(), match.end()


def register(registry: ToolRegistry, context: ToolContext) -> None:
    files = context.files
    user_id = context.user_id

    @registry.tool(
        name="search_uploaded_files",
        description=(
            "Search all uploaded files for a term and get back matching excerpts "
            "with character offsets (and PDF page numbers when available). Use "
            "this before read_uploaded_file on a long document: find where the "
            "answer is, then read that part."
        ),
        parameters={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Text to look for. Case-insensitive literal match.",
                },
                "name": {
                    "type": "string",
                    "description": "Optional: restrict the search to one file.",
                },
            },
            "required": ["query"],
        },
    )
    async def search_uploaded_files(query: str, name: str | None = None) -> str:
        needle = query.strip()
        if not needle:
            return "Error: query is empty."

        try:
            rows = (
                [await files.get(user_id, name)]
                if name
                else await files.list_for(user_id)
            )
        except UnknownFileError as exc:
            return f"Error: {exc}"
        if not rows:
            return "No files have been uploaded."

        blocks: list[str] = []
        for row in rows:
            try:
                content = await files.text(user_id, str(row.id))
            except (UnreadableFileError, UnknownFileError):
                continue

            hits: list[str] = []
            cursor = 0
            more = False
            while len(hits) < _MAX_HITS_PER_FILE:
                span = find_ci(content, needle, start=cursor)
                if span is None:
                    break
                start, end = span
                excerpt_start = max(0, start - _CONTEXT_CHARS)
                excerpt_end = min(len(content), end + _CONTEXT_CHARS)
                excerpt = " ".join(content[excerpt_start:excerpt_end].split())
                page = page_at_offset(content, start)
                where = (
                    f"page {page}, offset {start}" if page else f"offset {start}"
                )
                hits.append(f"  {where}: …{excerpt}…")
                cursor = end
            else:
                more = find_ci(content, needle, start=cursor) is not None

            if hits:
                suffix = " (more matches not shown)" if more else ""
                blocks.append(f"{row.name}{suffix}\n" + "\n".join(hits))

        if not blocks:
            return f"No matches for {query!r} in {len(rows)} file(s)."
        return "\n\n".join(blocks)
