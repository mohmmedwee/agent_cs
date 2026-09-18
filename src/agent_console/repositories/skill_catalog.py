"""Merged view of built-in (disk) skills and per-user (database) skills.

Progressive disclosure stays the same: the system prompt only gets name +
description lines; bodies are paid for when `read_skill` runs.
"""

from __future__ import annotations

from agent_console.db.models import UserSkill
from agent_console.models.skills import Skill
from agent_console.repositories.skills import SkillRepository, UnknownSkillError

__all__ = ["SkillCatalog"]


class SkillCatalog:
    """Per-request catalog: enabled user skills + built-ins (no name shadowing)."""

    def __init__(
        self,
        builtins: SkillRepository,
        user_skills: list[UserSkill],
    ) -> None:
        self._builtins = builtins
        # Enabled only — disabled stay out of the agent index.
        self._user = {row.name: row for row in user_skills if row.enabled}

    def list(self) -> list[Skill]:
        """Index entries for the agent (enabled user + builtins not overridden)."""
        found: dict[str, Skill] = {}
        for skill in self._builtins.list():
            found[skill.name] = skill
        for row in self._user.values():
            found[row.name] = Skill(
                name=row.name,
                description=row.description,
                path=None,
                source="user",
            )
        return sorted(found.values(), key=lambda skill: skill.name)

    def index(self) -> str:
        return "\n".join(skill.index_line() for skill in self.list())

    def read(self, name: str, max_chars: int | None = None) -> str:
        row = self._user.get(name)
        if row is not None:
            body = row.body
            if max_chars is None or len(body) <= max_chars:
                return body
            return (
                body[:max_chars]
                + f"\n\n[skill truncated at {max_chars} of {len(body)} characters]"
            )
        try:
            return self._builtins.read(name, max_chars=max_chars)
        except UnknownSkillError:
            available = ", ".join(s.name for s in self.list()) or "none"
            raise UnknownSkillError(
                f"no skill named {name!r}. Available: {available}"
            ) from None
