"""Read a web page as text, so the model can work from sources not snippets."""

import httpx

from agent_console.clients.search import SearchError
from agent_console.services.tools.context import ToolContext
from agent_console.services.tools.registry import ToolRegistry

__all__ = ["register"]


def register(registry: ToolRegistry, context: ToolContext) -> None:
    fetcher = context.pages

    @registry.tool(
        name="fetch_url",
        description=(
            "Fetch a web page or text document and return its readable text. "
            "Use after web_search to read a promising result, or when the user "
            "gives you a URL. Long pages are truncated."
        ),
        parameters={
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "Absolute http(s) URL."}
            },
            "required": ["url"],
        },
    )
    async def fetch_url(url: str) -> str:
        try:
            return await fetcher.fetch(url)
        except SearchError as exc:
            return f"Error: {exc}"
        except httpx.HTTPStatusError as exc:
            return f"Error: {url} returned HTTP {exc.response.status_code}"
        except httpx.HTTPError as exc:
            return f"Error: could not fetch {url} — {type(exc).__name__}: {exc}"
