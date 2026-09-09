"""Persistence. Swap implementations here without touching services."""

from agent_console.repositories.conversations import (
    ConversationRepository,
    UnknownConversationError,
)
from agent_console.repositories.documents import DOCX_MEDIA_TYPE, build_docx
from agent_console.repositories.extraction import extract_text
from agent_console.repositories.files import (
    FileRepository,
    FileTooLargeError,
    UnknownFileError,
    UnreadableFileError,
)
from agent_console.repositories.skills import SkillRepository, UnknownSkillError
from agent_console.repositories.users import EmailTakenError, UserRepository

__all__ = [
    "DOCX_MEDIA_TYPE",
    "ConversationRepository",
    "EmailTakenError",
    "FileRepository",
    "FileTooLargeError",
    "SkillRepository",
    "UnknownConversationError",
    "UnknownFileError",
    "UnknownSkillError",
    "UnreadableFileError",
    "UserRepository",
    "build_docx",
    "extract_text",
]
