"""Domain types for agent skills."""

from pathlib import Path

from pydantic import BaseModel

__all__ = ["Skill"]


class Skill(BaseModel):
    """A SKILL.md file: a name, a description, and a body loaded on demand.

    Only `name` and `description` reach the system prompt. The body costs
    nothing until the model decides the skill is relevant and reads it.
    """

    name: str
    description: str
    path: Path

    def index_line(self) -> str:
        return f"- {self.name}: {self.description}"
