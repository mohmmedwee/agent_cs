"""Outbound clients. Nothing here knows about HTTP request handling."""

from agent_console.clients.search import (
    DuckDuckGoBackend,
    PageFetcher,
    SearchBackend,
    SearchError,
)
from agent_console.clients.streaming import (
    ToolCallAccumulator,
    parse_sse_line,
    salvage_text_call,
)
from agent_console.clients.upstream import CompletionChunk, UpstreamClient, UpstreamError

__all__ = [
    "CompletionChunk",
    "DuckDuckGoBackend",
    "PageFetcher",
    "SearchBackend",
    "SearchError",
    "ToolCallAccumulator",
    "UpstreamClient",
    "UpstreamError",
    "parse_sse_line",
    "salvage_text_call",
]
