"""Persistence. Swap implementations here without touching services."""

from agent_console.repositories.extraction import extract_text
from agent_console.repositories.files import (
    FileRepository,
    FileTooLargeError,
    UnknownFileError,
    UnreadableFileError,
)
from agent_console.repositories.skills import SkillRepository, UnknownSkillError

__all__ = [
    "FileRepository",
    "FileTooLargeError",
    "SkillRepository",
    "UnknownFileError",
    "UnknownSkillError",
    "UnreadableFileError",
    "extract_text",
]
