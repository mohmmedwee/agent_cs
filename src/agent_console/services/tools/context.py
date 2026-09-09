"""Dependencies a tool may need at registration time."""

from dataclasses import dataclass

from agent_console.clients.search import PageFetcher, SearchBackend
from agent_console.config import Settings
from agent_console.repositories.files import FileRepository
from agent_console.repositories.skills import SkillRepository

__all__ = ["ToolContext"]


@dataclass(frozen=True, slots=True)
class ToolContext:
    """Passed to every tool module's `register()`.

    Add a field here when a new tool needs a collaborator, rather than importing
    it inside the tool — that keeps tools constructible in tests.
    """

    settings: Settings
    files: FileRepository
    skills: SkillRepository
    search: SearchBackend
    pages: PageFetcher
