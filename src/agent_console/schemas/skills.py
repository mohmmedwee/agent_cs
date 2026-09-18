"""Request and response shapes for skills (built-in + user-authored)."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

__all__ = [
    "SkillGenerateRequest",
    "SkillGenerateResponse",
    "SkillListResponse",
    "SkillSummary",
    "UserSkillCreateRequest",
    "UserSkillResponse",
    "UserSkillUpdateRequest",
]


class SkillSummary(BaseModel):
    """One line in the skills UI / agent index (no body)."""

    name: str
    description: str
    source: str = "builtin"
    id: UUID | None = None
    enabled: bool = True


class SkillListResponse(BaseModel):
    skills: list[SkillSummary]


class UserSkillCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    description: str = Field(min_length=1, max_length=500)
    body: str = Field(min_length=1, max_length=20_000)
    enabled: bool = True


class UserSkillUpdateRequest(BaseModel):
    description: str | None = Field(default=None, min_length=1, max_length=500)
    body: str | None = Field(default=None, min_length=1, max_length=20_000)
    enabled: bool | None = None


class UserSkillResponse(BaseModel):
    id: UUID
    name: str
    description: str
    body: str
    enabled: bool
    created_at: datetime
    updated_at: datetime
    source: str = "user"

    model_config = {"from_attributes": True}


class SkillGenerateRequest(BaseModel):
    prompt: str = Field(min_length=3, max_length=2000)
    model: str | None = None


class SkillGenerateResponse(BaseModel):
    name: str
    description: str
    body: str
