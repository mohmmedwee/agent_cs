"""CRUD for durable user memories (also writable via agent tools)."""

from uuid import UUID

from fastapi import APIRouter, HTTPException, status

from agent_console.api.dependencies import CurrentUserDep, MemoryRepositoryDep
from agent_console.repositories.memory import MemoryLimitError, UnknownMemoryError
from agent_console.schemas.memory import (
    MemoryCreateRequest,
    MemoryListResponse,
    MemoryResponse,
    MemoryUpdateRequest,
)

__all__ = ["router"]

router = APIRouter(prefix="/api/memory", tags=["memory"])


@router.get("")
async def list_memories(
    user: CurrentUserDep, repository: MemoryRepositoryDep
) -> MemoryListResponse:
    rows = await repository.list_for(user.id)
    return MemoryListResponse(memories=[MemoryResponse.model_validate(row) for row in rows])


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_memory(
    payload: MemoryCreateRequest,
    user: CurrentUserDep,
    repository: MemoryRepositoryDep,
) -> MemoryResponse:
    try:
        row = await repository.add(user.id, payload.content, source="user")
    except MemoryLimitError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    return MemoryResponse.model_validate(row)


@router.patch("/{memory_id}")
async def update_memory(
    memory_id: UUID,
    payload: MemoryUpdateRequest,
    user: CurrentUserDep,
    repository: MemoryRepositoryDep,
) -> MemoryResponse:
    try:
        row = await repository.update(user.id, memory_id, payload.content)
    except UnknownMemoryError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    except MemoryLimitError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    return MemoryResponse.model_validate(row)


@router.delete("/{memory_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_memory(
    memory_id: UUID,
    user: CurrentUserDep,
    repository: MemoryRepositoryDep,
) -> None:
    try:
        await repository.delete(user.id, memory_id)
    except UnknownMemoryError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
