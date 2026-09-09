"""Streaming chat endpoint, persisted against a conversation."""

import asyncio
import json
import logging
from collections.abc import AsyncIterable
from uuid import UUID

import httpx
from fastapi import APIRouter, HTTPException, Request, status
from fastapi.sse import EventSourceResponse
from pydantic import BaseModel, Field

from agent_console.api.dependencies import (
    AgentServiceDep,
    ApprovalBrokerDep,
    CurrentUserDep,
    SettingsDep,
    UpstreamClientDep,
)
from agent_console.clients.upstream import UpstreamError
from agent_console.repositories.conversations import (
    ConversationRepository,
    UnknownConversationError,
)
from agent_console.schemas.chat import (
    ChatRequest,
    ModelInfo,
    ModelListResponse,
    ToolApprovalRequest,
)
from agent_console.services.approvals import ApprovalBroker
from agent_console.services.chat_jobs import ChatJobBroker
from agent_console.services.context_compact import prepare_model_messages

__all__ = ["router"]

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["chat"])


class StopChatRequest(BaseModel):
    conversation_id: UUID


@router.post("/chat", response_model=None)
async def chat(
    request: ChatRequest,
    http_request: Request,
    user: CurrentUserDep,
    agent: AgentServiceDep,
    settings: SettingsDep,
    upstream: UpstreamClientDep,
) -> EventSourceResponse:
    """Run the agent loop, streaming typed events as they happen.

    The producer runs as a background task keyed by conversation. If the client
    leaves the page (or the SSE consumer is cancelled), the agent keeps going
    and the turn is still persisted. Explicit Stop cancels that job.
    """
    factory = http_request.app.state.session_factory
    jobs: ChatJobBroker = http_request.app.state.chat_jobs
    user_id = user.id

    async with factory() as session:
        conversations = ConversationRepository(session)
        try:
            conversation = await conversations.get(user_id, request.conversation_id)
        except UnknownConversationError as exc:
            raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc

        history = [
            {"role": message.role, "content": message.content}
            for message in conversation.messages
            if message.content
        ]
        await conversations.append(
            user_id, request.conversation_id, role="user", content=request.message
        )
        transcript = [*history, {"role": "user", "content": request.message}]
        messages = await prepare_model_messages(
            conversation=conversation,
            transcript=transcript,
            settings=settings,
            upstream=upstream,
            model=request.model,
        )
        await session.commit()

    blocks: list[dict] = []
    text_parts: list[str] = []
    conversation_key = str(request.conversation_id)
    approvals: ApprovalBroker = http_request.app.state.approvals
    event_queue: asyncio.Queue[dict | None] = asyncio.Queue()
    cancel = asyncio.Event()

    async def produce() -> None:
        try:
            async for event in agent.run(
                messages,
                model=request.model,
                effort=request.effort,
                conversation_id=conversation_key,
            ):
                if cancel.is_set():
                    break
                payload = event.model_dump()
                _collect(payload, blocks, text_parts)
                await event_queue.put(payload)
        except asyncio.CancelledError:
            logger.info("chat job cancelled for %s", conversation_key)
            raise
        except Exception as exc:  # noqa: BLE001 — surface to the UI stream
            logger.exception("chat job failed for %s", conversation_key)
            error_payload = {"type": "error", "message": str(exc)}
            _collect(error_payload, blocks, text_parts)
            await event_queue.put(error_payload)
        finally:
            approvals.cancel_conversation(conversation_key)
            try:
                async with factory() as session:
                    await ConversationRepository(session).append(
                        user_id,
                        request.conversation_id,
                        role="assistant",
                        content="".join(text_parts),
                        blocks=blocks or None,
                    )
                    await session.commit()
            except Exception:
                logger.exception(
                    "failed to persist assistant turn for %s", request.conversation_id
                )
            await event_queue.put(None)

    jobs.spawn(conversation_key, produce(), cancel)

    async def stream() -> AsyncIterable[str]:
        try:
            while True:
                payload = await event_queue.get()
                if payload is None:
                    break
                yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
        except asyncio.CancelledError:
            # Client navigated away or closed the tab — producer keeps running.
            logger.info(
                "client left stream for %s; background job continues",
                conversation_key,
            )
            return

    return EventSourceResponse(
        stream(),
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/chat/stop", status_code=status.HTTP_204_NO_CONTENT)
async def stop_chat(
    body: StopChatRequest,
    user: CurrentUserDep,
    approvals: ApprovalBrokerDep,
    http_request: Request,
) -> None:
    """Explicitly cancel a background chat job (Stop button)."""
    factory = http_request.app.state.session_factory
    async with factory() as session:
        try:
            await ConversationRepository(session).get(user.id, body.conversation_id)
        except UnknownConversationError as exc:
            raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc

    key = str(body.conversation_id)
    jobs: ChatJobBroker = http_request.app.state.chat_jobs
    jobs.stop(key)
    approvals.cancel_conversation(key)


@router.post("/chat/approve", status_code=status.HTTP_204_NO_CONTENT)
async def approve_tool(
    body: ToolApprovalRequest,
    user: CurrentUserDep,
    approvals: ApprovalBrokerDep,
    http_request: Request,
) -> None:
    """Resume a paused tool call. Must own the conversation."""
    factory = http_request.app.state.session_factory
    async with factory() as session:
        conversations = ConversationRepository(session)
        try:
            await conversations.get(user.id, body.conversation_id)
        except UnknownConversationError as exc:
            raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc

    if not approvals.resolve(str(body.conversation_id), body.call_id, body.allowed):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "No pending approval for this tool call (expired or already decided).",
        )


def _collect(event: dict, blocks: list[dict], text_parts: list[str]) -> None:
    """Fold one event into the durable record of the turn.

    Reasoning is deliberately not stored: it is scratch work, it is large, and
    it is never replayed to the model.
    """
    kind = event.get("type")
    if kind == "text_delta":
        text_parts.append(event["text"])
        if blocks and blocks[-1].get("kind") == "text":
            blocks[-1]["text"] += event["text"]
        else:
            blocks.append({"kind": "text", "text": event["text"]})
    elif kind == "tool_call":
        blocks.append(
            {
                "kind": "skill" if event["name"] == "read_skill" else "tool",
                "id": event["id"],
                "name": event["name"],
                "args": event["arguments"],
            }
        )
    elif kind == "tool_result":
        for block in reversed(blocks):
            if block.get("id") == event["id"]:
                if block["kind"] == "tool":
                    block["result"] = event["result"]
                    block["failed"] = event["result"].startswith("Error:")
                break
    elif kind == "error":
        blocks.append({"kind": "error", "message": event["message"]})


@router.get("/models")
async def list_models(
    user: CurrentUserDep, upstream: UpstreamClientDep
) -> ModelListResponse:
    """The model picker's options.

    An unreachable endpoint returns an empty list rather than a 500: the rest
    of the settings screen still works, and the picker simply has nothing to
    offer.
    """
    try:
        names = await upstream.list_models()
        current = await upstream.resolve_model()
    except (httpx.HTTPError, UpstreamError):
        return ModelListResponse(models=[], current=None)

    return ModelListResponse(
        models=[ModelInfo(id=name, loaded=name == current) for name in names],
        current=current,
    )
