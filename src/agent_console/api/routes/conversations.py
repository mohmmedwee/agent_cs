"""Conversation list and detail. Every route is scoped to the signed-in user."""

from uuid import UUID

from fastapi import APIRouter, HTTPException, status

from agent_console.api.dependencies import ConversationRepositoryDep, CurrentUserDep
from agent_console.repositories.conversations import UnknownConversationError
from agent_console.schemas.conversations import (
    ConversationDetail,
    ConversationListResponse,
    ConversationSummary,
    CreateConversationRequest,
    RenameConversationRequest,
    RewindConversationRequest,
)

__all__ = ["router"]

router = APIRouter(prefix="/api/conversations", tags=["conversations"])


@router.get("")
async def list_conversations(
    user: CurrentUserDep, repository: ConversationRepositoryDep
) -> ConversationListResponse:
    rows = await repository.list_for(user.id)
    return ConversationListResponse(
        conversations=[ConversationSummary.model_validate(row) for row in rows]
    )


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_conversation(
    payload: CreateConversationRequest,
    user: CurrentUserDep,
    repository: ConversationRepositoryDep,
) -> ConversationSummary:
    row = await repository.create(user.id, payload.title)
    return ConversationSummary.model_validate(row)


@router.get("/{conversation_id}")
async def get_conversation(
    conversation_id: UUID,
    user: CurrentUserDep,
    repository: ConversationRepositoryDep,
) -> ConversationDetail:
    try:
        row = await repository.get(user.id, conversation_id)
    except UnknownConversationError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    return ConversationDetail.from_row(row)


@router.patch("/{conversation_id}")
async def rename_conversation(
    conversation_id: UUID,
    payload: RenameConversationRequest,
    user: CurrentUserDep,
    repository: ConversationRepositoryDep,
) -> ConversationSummary:
    try:
        row = await repository.rename(user.id, conversation_id, payload.title)
    except UnknownConversationError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    return ConversationSummary.model_validate(row)


@router.post("/{conversation_id}/rewind")
async def rewind_conversation(
    conversation_id: UUID,
    payload: RewindConversationRequest,
    user: CurrentUserDep,
    repository: ConversationRepositoryDep,
) -> ConversationDetail:
    """Delete from message index `keep` onward — used when editing a prompt."""
    try:
        row = await repository.truncate_from(user.id, conversation_id, payload.keep)
    except UnknownConversationError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    return ConversationDetail.from_row(row)


@router.delete("/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_conversation(
    conversation_id: UUID,
    user: CurrentUserDep,
    repository: ConversationRepositoryDep,
) -> None:
    try:
        await repository.delete(user.id, conversation_id)
    except UnknownConversationError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
