"""Read-only view of the loaded skills, for the UI and for debugging."""

from fastapi import APIRouter

from agent_console.api.dependencies import SkillRepositoryDep
from agent_console.schemas.skills import SkillListResponse

__all__ = ["router"]

router = APIRouter(prefix="/api/skills", tags=["skills"])


@router.get("")
async def list_skills(repository: SkillRepositoryDep) -> SkillListResponse:
    return SkillListResponse(skills=repository.list())
