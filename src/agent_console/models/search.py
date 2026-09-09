"""Domain types for web search."""

from pydantic import BaseModel

__all__ = ["SearchResult"]


class SearchResult(BaseModel):
    title: str
    url: str
    snippet: str = ""

    def as_line(self) -> str:
        snippet = self.snippet.strip().replace("\n", " ")
        return f"{self.title}\n  {self.url}\n  {snippet}" if snippet else f"{self.title}\n  {self.url}"
