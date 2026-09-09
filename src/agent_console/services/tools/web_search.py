"""Search the web. Pairs with fetch_url: search finds pages, fetch reads them."""

import asyncio

from agent_console.clients.search import SearchError
from agent_console.services.tools.context import ToolContext
from agent_console.services.tools.registry import ToolRegistry

__all__ = ["register"]


def register(registry: ToolRegistry, context: ToolContext) -> None:
    backend = context.search
    cache = context.cache
    default_results = context.settings.search_results
    ttl = context.settings.cache_search_ttl

    @registry.tool(
        name="web_search",
        description=(
            "Search the web and get back titles, URLs, and snippets. "
            "Use for anything current, external, or that you are not certain of. "
            "Snippets are previews only — call fetch_url on a result to read it."
        ),
        parameters={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search terms. Be specific; add a year for recent topics.",
                },
                "max_results": {
                    "type": "integer",
                    "description": f"How many results to return. Defaults to {default_results}.",
                },
            },
            "required": ["query"],
        },
    )
    async def web_search(query: str, max_results: int | None = None) -> str:
        count = max(1, min(int(max_results or default_results), 10))
        cache_key = f"{count}:{query.strip().lower()}"

        if hit := await cache.get("search", cache_key):
            return hit

        try:
            # The backend is blocking; keep it off the event loop.
            results = await asyncio.to_thread(backend.search, query, count)
        except SearchError as exc:
            return f"Error: search failed — {exc}"

        if not results:
            return f"No results for {query!r}."

        rendered = "\n\n".join(result.as_line() for result in results)
        await cache.set("search", cache_key, rendered, ttl)
        return rendered
