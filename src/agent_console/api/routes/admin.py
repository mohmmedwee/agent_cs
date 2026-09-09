"""Admin-only endpoints."""

from fastapi import APIRouter

from agent_console.api.dependencies import AdminDep, UserRepositoryDep
from agent_console.schemas.auth import UserListResponse, UserResponse

__all__ = ["router"]

router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.get("/users")
async def list_users(admin: AdminDep, users: UserRepositoryDep) -> UserListResponse:
    rows = await users.list_all()
    return UserListResponse(users=[UserResponse.model_validate(row) for row in rows])
