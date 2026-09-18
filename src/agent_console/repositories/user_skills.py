"""Durable per-user skills (Markdown instructions for the agent)."""

from __future__ import annotations

import re
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from agent_console.db.models import UserSkill

__all__ = [
    "UserSkillRepository",
    "SkillLimitError",
    "SkillNameError",
    "UnknownUserSkillError",
    "slugify_skill_name",
]

_NAME_RE = re.compile(r"^[a-z][a-z0-9-]{0,62}$")
_NON_SLUG = re.compile(r"[^a-z0-9]+")


def slugify_skill_name(name: str) -> str:
    """Turn 'Oustah Guidelines' into 'oustah-guidelines'."""
    cleaned = _NON_SLUG.sub("-", name.strip().lower()).strip("-")
    return cleaned[:63]


class UnknownUserSkillError(LookupError):
    """No skill with that id belongs to this user."""


class SkillLimitError(ValueError):
    """Too many skills or content that is too long."""


class SkillNameError(ValueError):
    """Invalid or reserved skill name."""


class UserSkillRepository:
    def __init__(
        self,
        session: AsyncSession,
        *,
        max_items: int = 20,
        max_body_chars: int = 12_000,
        max_description_chars: int = 500,
        reserved_names: set[str] | None = None,
    ) -> None:
        self._session = session
        self._max_items = max_items
        self._max_body_chars = max_body_chars
        self._max_description_chars = max_description_chars
        self._reserved = reserved_names or set()

    async def list_for(self, user_id: UUID) -> list[UserSkill]:
        result = await self._session.execute(
            select(UserSkill)
            .where(UserSkill.user_id == user_id)
            .order_by(UserSkill.updated_at.desc())
        )
        return list(result.scalars())

    async def list_enabled(self, user_id: UUID) -> list[UserSkill]:
        result = await self._session.execute(
            select(UserSkill)
            .where(UserSkill.user_id == user_id, UserSkill.enabled.is_(True))
            .order_by(UserSkill.name.asc())
        )
        return list(result.scalars())

    async def get(self, user_id: UUID, skill_id: UUID) -> UserSkill:
        result = await self._session.execute(
            select(UserSkill).where(
                UserSkill.id == skill_id,
                UserSkill.user_id == user_id,
            )
        )
        row = result.scalar_one_or_none()
        if row is None:
            raise UnknownUserSkillError(f"no skill {skill_id}")
        return row

    async def get_by_name(self, user_id: UUID, name: str) -> UserSkill | None:
        result = await self._session.execute(
            select(UserSkill).where(
                UserSkill.user_id == user_id,
                UserSkill.name == name,
            )
        )
        return result.scalar_one_or_none()

    async def count_for(self, user_id: UUID) -> int:
        result = await self._session.execute(
            select(func.count())
            .select_from(UserSkill)
            .where(UserSkill.user_id == user_id)
        )
        return int(result.scalar_one())

    def _clean_name(self, name: str) -> str:
        cleaned = slugify_skill_name(name)
        if not cleaned or not _NAME_RE.match(cleaned):
            raise SkillNameError(
                "skill name must start with a letter and use only "
                "lowercase letters, digits, and hyphens (max 63 chars). "
                "Example: oustah-guidelines"
            )
        if cleaned in self._reserved:
            raise SkillNameError(
                f"skill name {cleaned!r} is reserved for a built-in skill"
            )
        return cleaned

    def _clean_description(self, description: str) -> str:
        text = " ".join(description.strip().split())
        if not text:
            raise SkillLimitError("description cannot be empty")
        if len(text) > self._max_description_chars:
            raise SkillLimitError(
                f"description is {len(text)} characters; "
                f"limit is {self._max_description_chars}"
            )
        return text

    def _clean_body(self, body: str) -> str:
        text = body.strip()
        if not text:
            raise SkillLimitError("skill body cannot be empty")
        if len(text) > self._max_body_chars:
            raise SkillLimitError(
                f"skill body is {len(text)} characters; "
                f"limit is {self._max_body_chars}"
            )
        return text

    async def create(
        self,
        user_id: UUID,
        *,
        name: str,
        description: str,
        body: str,
        enabled: bool = True,
    ) -> UserSkill:
        cleaned_name = self._clean_name(name)
        if await self.count_for(user_id) >= self._max_items:
            raise SkillLimitError(
                f"already at the limit of {self._max_items} custom skills"
            )
        if await self.get_by_name(user_id, cleaned_name) is not None:
            raise SkillNameError(f"you already have a skill named {cleaned_name!r}")
        row = UserSkill(
            user_id=user_id,
            name=cleaned_name,
            description=self._clean_description(description),
            body=self._clean_body(body),
            enabled=enabled,
        )
        self._session.add(row)
        await self._session.flush()
        return row

    async def update(
        self,
        user_id: UUID,
        skill_id: UUID,
        *,
        description: str | None = None,
        body: str | None = None,
        enabled: bool | None = None,
    ) -> UserSkill:
        row = await self.get(user_id, skill_id)
        if description is not None:
            row.description = self._clean_description(description)
        if body is not None:
            row.body = self._clean_body(body)
        if enabled is not None:
            row.enabled = enabled
        await self._session.flush()
        return row

    async def delete(self, user_id: UUID, skill_id: UUID) -> None:
        row = await self.get(user_id, skill_id)
        await self._session.delete(row)
        await self._session.flush()
