"""Domain types for agent skills."""

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

__all__ = ["Skill"]


class Skill(BaseModel):
    """A skill: a name, a description, and a body loaded on demand.

    Only `name` and `description` reach the system prompt. The body costs
    nothing until the model decides the skill is relevant and reads it.
    Built-ins have a filesystem `path`; user skills are stored in the database.
    """

    model_config = ConfigDict()

    name: str
    description: str
    path: Path | None = Field(default=None, exclude=True)
    source: Literal["builtin", "user"] = "builtin"

    def index_line(self) -> str:
        return f"- {self.name}: {self.description}"
