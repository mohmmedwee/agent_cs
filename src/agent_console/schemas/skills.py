"""Response schemas for the skills endpoint."""

from pydantic import BaseModel

from agent_console.models.skills import Skill

__all__ = ["SkillListResponse"]


class SkillListResponse(BaseModel):
    skills: list[Skill]
