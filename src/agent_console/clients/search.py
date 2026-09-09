"""Web search and page fetching.

Search goes through DuckDuckGo because it needs no API key, which keeps the
default install working with zero configuration. The `SearchBackend` protocol
is the seam: add a Brave or Tavily implementation and select it in Settings
without touching the tool or the agent.
"""

import re
from html.parser import HTMLParser
from typing import Protocol

import httpx

from agent_console.models.search import SearchResult

__all__ = ["DuckDuckGoBackend", "PageFetcher", "SearchBackend", "SearchError"]


class SearchError(RuntimeError):
    """The search backend could not answer."""


class SearchBackend(Protocol):
    def search(self, query: str, max_results: int) -> list[SearchResult]: ...


class DuckDuckGoBackend:
    """Blocking; callers run it in a thread. No API key required."""

    def search(self, query: str, max_results: int) -> list[SearchResult]:
        try:
            from ddgs import DDGS
        except ImportError as exc:  # pragma: no cover - dependency is declared
            raise SearchError("the 'ddgs' package is not installed") from exc

        try:
            with DDGS() as client:
                rows = list(client.text(query, max_results=max_results))
        except Exception as exc:
            raise SearchError(f"{type(exc).__name__}: {exc}") from exc

        return [
            SearchResult(
                title=row.get("title") or row.get("href") or "untitled",
                url=row.get("href") or "",
                snippet=row.get("body") or "",
            )
            for row in rows
            if row.get("href")
        ]


class _TextExtractor(HTMLParser):
    """Collect visible text. Deliberately stdlib — this may run air-gapped."""

    _SKIP = {"script", "style", "noscript", "svg", "head", "nav", "footer", "form"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._parts: list[str] = []
        self._depth = 0

    def handle_starttag(self, tag: str, attrs: list) -> None:
        if tag in self._SKIP:
            self._depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag in self._SKIP and self._depth:
            self._depth -= 1

    def handle_data(self, data: str) -> None:
        if not self._depth and data.strip():
            self._parts.append(data.strip())

    def text(self) -> str:
        return re.sub(r"\n{3,}", "\n\n", "\n".join(self._parts))


class PageFetcher:
    """Fetches a URL and reduces it to readable text."""

    def __init__(self, http: httpx.AsyncClient, timeout: float, max_chars: int) -> None:
        self._http = http
        self._timeout = timeout
        self._max_chars = max_chars

    async def fetch(self, url: str) -> str:
        if not url.startswith(("http://", "https://")):
            raise SearchError("only http and https URLs can be fetched")

        response = await self._http.get(
            url,
            timeout=self._timeout,
            follow_redirects=True,
            headers={"User-Agent": "agent-console/0.1 (+local research tool)"},
        )
        response.raise_for_status()

        content_type = response.headers.get("content-type", "")
        if "html" in content_type:
            parser = _TextExtractor()
            parser.feed(response.text)
            body = parser.text()
        elif content_type.startswith("text/") or "json" in content_type:
            body = response.text
        else:
            raise SearchError(f"cannot read {content_type or 'unknown'} as text")

        if len(body) <= self._max_chars:
            return body
        return body[: self._max_chars] + f"\n\n[truncated at {self._max_chars} characters]"
