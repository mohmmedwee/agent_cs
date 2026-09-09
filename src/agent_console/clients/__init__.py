"""Outbound integrations. Nothing here knows about application logic."""

from agent_console.clients.cache import ResponseCache
from agent_console.clients.search import (
    DuckDuckGoBackend,
    PageFetcher,
    SearchBackend,
    SearchError,
)
from agent_console.clients.upstream import CompletionChunk, UpstreamClient, UpstreamError

__all__ = [
    "CompletionChunk",
    "DuckDuckGoBackend",
    "PageFetcher",
    "ResponseCache",
    "SearchBackend",
    "SearchError",
    "UpstreamClient",
    "UpstreamError",
]
