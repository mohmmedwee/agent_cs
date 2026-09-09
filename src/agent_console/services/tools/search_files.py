"""Find a term across uploaded documents without reading them whole.

Reading a long document into the conversation costs prefill on every later
step. Searching first lets the model locate the relevant passage and spend its
context on that instead.
"""

from agent_console.repositories.files import UnknownFileError, UnreadableFileError
from agent_console.services.tools.context import ToolContext
from agent_console.services.tools.registry import ToolRegistry

__all__ = ["register"]

_CONTEXT_CHARS = 160
_MAX_HITS_PER_FILE = 5


def register(registry: ToolRegistry, context: ToolContext) -> None:
    files = context.files
    user_id = context.user_id

    @registry.tool(
        name="search_uploaded_files",
        description=(
            "Search all uploaded files for a term and get back matching excerpts "
            "with their character offsets. Use this before read_uploaded_file on "
            "a long document: find where the answer is, then read that part."
        ),
        parameters={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Text to look for. Case-insensitive."},
                "name": {
                    "type": "string",
                    "description": "Optional: restrict the search to one file.",
                },
            },
            "required": ["query"],
        },
    )
    async def search_uploaded_files(query: str, name: str | None = None) -> str:
        needle = query.strip().lower()
        if not needle:
            return "Error: query is empty."

        try:
            rows = [await files.get(user_id, name)] if name else await files.list_for(user_id)
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
            haystack = content.lower()
            position = haystack.find(needle)
            while position != -1 and len(hits) < _MAX_HITS_PER_FILE:
                start = max(0, position - _CONTEXT_CHARS)
                end = min(len(content), position + len(needle) + _CONTEXT_CHARS)
                excerpt = " ".join(content[start:end].split())
                hits.append(f"  offset {position}: …{excerpt}…")
                position = haystack.find(needle, position + len(needle))

            if hits:
                more = " (more matches not shown)" if position != -1 else ""
                blocks.append(f"{row.name}{more}\n" + "\n".join(hits))

        if not blocks:
            return f"No matches for {query!r} in {len(rows)} file(s)."
        return "\n\n".join(blocks)
