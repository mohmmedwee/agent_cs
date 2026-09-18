"""Built-in skill index plus CRUD for user-authored skills."""

from uuid import UUID

from fastapi import APIRouter, HTTPException, status

from agent_console.api.dependencies import (
    CurrentUserDep,
    SkillRepositoryDep,
    UpstreamClientDep,
    UserSkillRepositoryDep,
)
from agent_console.repositories.user_skills import (
    SkillLimitError,
    SkillNameError,
    UnknownUserSkillError,
)
from agent_console.schemas.skills import (
    SkillGenerateRequest,
    SkillGenerateResponse,
    SkillListResponse,
    SkillSummary,
    UserSkillCreateRequest,
    UserSkillResponse,
    UserSkillUpdateRequest,
)
from agent_console.services.skill_generate import (
    SkillGenerateError,
    generate_skill_draft,
)

__all__ = ["router"]

router = APIRouter(prefix="/api/skills", tags=["skills"])


@router.get("")
async def list_skills(
    user: CurrentUserDep,
    builtins: SkillRepositoryDep,
    user_skills: UserSkillRepositoryDep,
) -> SkillListResponse:
    rows = await user_skills.list_for(user.id)
    summaries = [
        SkillSummary(
            name=skill.name,
            description=skill.description,
            source="builtin",
        )
        for skill in builtins.list()
    ]
    summaries.extend(
        SkillSummary(
            id=row.id,
            name=row.name,
            description=row.description,
            source="user",
            enabled=row.enabled,
        )
        for row in rows
    )
    return SkillListResponse(skills=summaries)


@router.post("/generate")
async def generate_skill(
    payload: SkillGenerateRequest,
    user: CurrentUserDep,
    upstream: UpstreamClientDep,
    builtins: SkillRepositoryDep,
) -> SkillGenerateResponse:
    _ = user  # auth gate only
    try:
        draft = await generate_skill_draft(
            upstream=upstream,
            prompt=payload.prompt,
            model=payload.model,
            builtins=builtins,
        )
    except SkillGenerateError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    return SkillGenerateResponse(**draft)


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_skill(
    payload: UserSkillCreateRequest,
    user: CurrentUserDep,
    user_skills: UserSkillRepositoryDep,
) -> UserSkillResponse:
    try:
        row = await user_skills.create(
            user.id,
            name=payload.name,
            description=payload.description,
            body=payload.body,
            enabled=payload.enabled,
        )
    except (SkillLimitError, SkillNameError) as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    return UserSkillResponse.model_validate(row)


@router.get("/{skill_id}")
async def get_skill(
    skill_id: UUID,
    user: CurrentUserDep,
    user_skills: UserSkillRepositoryDep,
) -> UserSkillResponse:
    try:
        row = await user_skills.get(user.id, skill_id)
    except UnknownUserSkillError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    return UserSkillResponse.model_validate(row)


@router.patch("/{skill_id}")
async def update_skill(
    skill_id: UUID,
    payload: UserSkillUpdateRequest,
    user: CurrentUserDep,
    user_skills: UserSkillRepositoryDep,
) -> UserSkillResponse:
    try:
        row = await user_skills.update(
            user.id,
            skill_id,
            description=payload.description,
            body=payload.body,
            enabled=payload.enabled,
        )
    except UnknownUserSkillError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    except (SkillLimitError, SkillNameError) as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    return UserSkillResponse.model_validate(row)


@router.delete("/{skill_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_skill(
    skill_id: UUID,
    user: CurrentUserDep,
    user_skills: UserSkillRepositoryDep,
) -> None:
    try:
        await user_skills.delete(user.id, skill_id)
    except UnknownUserSkillError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
