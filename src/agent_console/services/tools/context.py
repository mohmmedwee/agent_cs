from dataclasses import dataclass
from uuid import UUID

from agent_console.clients.cache import ResponseCache
from agent_console.clients.search import PageFetcher, SearchBackend
from agent_console.clients.upstream import UpstreamClient
from agent_console.config import Settings
from agent_console.repositories.files import FileRepository
from agent_console.repositories.skills import SkillRepository

__all__ = ["ToolContext"]


@dataclass(frozen=True, slots=True)
class ToolContext:
    """Passed to every tool module's `register()`.

    Built per request, not once at startup, because `user_id` scopes every file
    operation. That is what stops one account reaching another's uploads.

    Add a field here when a new tool needs a collaborator, rather than importing
    it inside the tool — that keeps tools constructible in tests.
    """

    settings: Settings
    files: FileRepository
    skills: SkillRepository
    search: SearchBackend
    pages: PageFetcher
    cache: ResponseCache
    user_id: UUID
    # Lets `view_image` reach a multimodal model without the chat loop having
    # to know that the reasoning model is text-only.
    upstream: UpstreamClient
