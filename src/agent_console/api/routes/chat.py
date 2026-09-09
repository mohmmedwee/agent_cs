"""Streaming chat endpoint, persisted against a conversation."""

import json
import logging
from collections.abc import AsyncIterable

import httpx
from fastapi import APIRouter, HTTPException, Request, status
from fastapi.sse import EventSourceResponse

from agent_console.api.dependencies import (
    AgentServiceDep,
    CurrentUserDep,
    UpstreamClientDep,
)
from agent_console.clients.upstream import UpstreamError
from agent_console.repositories.conversations import (
    ConversationRepository,
    UnknownConversationError,
)
from agent_console.schemas.chat import ChatRequest, ModelInfo, ModelListResponse

__all__ = ["router"]

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["chat"])


@router.post("/chat", response_model=None)
async def chat(
    request: ChatRequest,
    http_request: Request,
    user: CurrentUserDep,
    agent: AgentServiceDep,
) -> EventSourceResponse:
    """Run the agent loop, streaming typed events as they happen.

    Persistence uses its own short sessions, not the request-scoped one the
    tools share. A long `write_file` generation can outlive the client's
    patience; when the stream is cancelled, rolling back that shared session
    used to erase the user turn and every block the UI had already shown.
    """
    factory = http_request.app.state.session_factory

    async with factory() as session:
        conversations = ConversationRepository(session)
        try:
            history = await conversations.history(user.id, request.conversation_id)
        except UnknownConversationError as exc:
            raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc

        await conversations.append(
            user.id, request.conversation_id, role="user", content=request.message
        )
        await session.commit()

    messages = [*history, {"role": "user", "content": request.message}]
    blocks: list[dict] = []
    text_parts: list[str] = []

    async def stream() -> AsyncIterable[str]:
        # Frames are built here rather than by yielding dicts from the path
        # operation, because that form cannot also return a 404 for an unknown
        # conversation — the body would not run until streaming had begun.
        try:
            async for event in agent.run(
                messages, model=request.model, effort=request.effort
            ):
                payload = event.model_dump()
                _collect(payload, blocks, text_parts)
                yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
        finally:
            # Own session: survives the request-scoped session being cancelled
            # mid-teardown, which is what left this conversation with only the
            # first turn after a long "writing the document" hang.
            try:
                async with factory() as session:
                    await ConversationRepository(session).append(
                        user.id,
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

    return EventSourceResponse(
        stream(),
        headers={
            "Cache-Control": "no-cache",
            # nginx buffers proxied responses by default, which would hold the
            # whole stream back until the run finished.
            "X-Accel-Buffering": "no",
        },
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
