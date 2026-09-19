"""Streaming chat endpoint, persisted against a conversation."""

import asyncio
import json
import logging
from collections.abc import AsyncIterable
from uuid import UUID

import httpx
from fastapi import APIRouter, HTTPException, Request, status
from fastapi.sse import EventSourceResponse
from pydantic import BaseModel

from agent_console.api.dependencies import (
    ApprovalBrokerDep,
    CurrentUserDep,
    SettingsDep,
    UpstreamClientDep,
)
from agent_console.clients.search import PageFetcher
from agent_console.clients.upstream import UpstreamError
from agent_console.repositories.conversations import (
    ConversationRepository,
    UnknownConversationError,
)
from agent_console.repositories.files import FileRepository
from agent_console.repositories.memory import MemoryRepository
from agent_console.repositories.skill_catalog import SkillCatalog
from agent_console.repositories.user_skills import UserSkillRepository
from agent_console.schemas.chat import (
    ChatRequest,
    ModelInfo,
    ModelListResponse,
    ToolApprovalRequest,
)
from agent_console.services.agent import AgentService
from agent_console.services.approvals import ApprovalBroker
from agent_console.services.auto_title import maybe_refine_title
from agent_console.services.chat_jobs import ChatJobBroker
from agent_console.services.context_compact import prepare_model_messages
from agent_console.services.tools import ToolContext, build_registry

__all__ = ["router"]

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["chat"])


class StopChatRequest(BaseModel):
    conversation_id: UUID


class WatchChatRequest(BaseModel):
    conversation_id: UUID


@router.post("/chat", response_model=None)
async def chat(
    request: ChatRequest,
    http_request: Request,
    user: CurrentUserDep,
    settings: SettingsDep,
    upstream: UpstreamClientDep,
) -> EventSourceResponse:
    """Run the agent loop, streaming typed events as they happen.

    The producer owns its own DB session and keeps running if the client
    disconnects (refresh / navigate away). Only POST /chat/stop cancels it.
    """
    factory = http_request.app.state.session_factory
    jobs: ChatJobBroker = http_request.app.state.chat_jobs
    approvals: ApprovalBroker = http_request.app.state.approvals
    user_id = user.id
    state = http_request.app.state

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
    cancel = asyncio.Event()

    async def produce() -> None:
        # Own session for the whole run — must outlive the HTTP request that
        # spawned us, otherwise a page refresh closes the request session and
        # kills tool calls mid-generation.
        try:
            async with factory() as session:
                files = FileRepository(
                    session, state.blob_store, settings.max_upload_bytes
                )
                memories = MemoryRepository(
                    session,
                    max_items=settings.max_memory_items,
                    max_chars=settings.max_memory_chars,
                )
                user_skills = UserSkillRepository(
                    session,
                    max_items=settings.max_user_skills,
                    max_body_chars=settings.max_user_skill_body_chars,
                    reserved_names=state.skill_repository.names(),
                )
                skills = SkillCatalog(
                    state.skill_repository,
                    await user_skills.list_enabled(user_id),
                )
                tools = build_registry(
                    ToolContext(
                        settings=settings,
                        files=files,
                        memories=memories,
                        skills=skills,
                        search=state.search_backend,
                        pages=PageFetcher(
                            http=state.http_client,
                            timeout=settings.fetch_timeout,
                            max_chars=settings.max_page_chars,
                        ),
                        cache=state.cache,
                        user_id=user_id,
                        upstream=upstream,
                    )
                )
                agent = AgentService(
                    upstream=upstream,
                    tools=tools,
                    settings=settings,
                    skills=skills,
                    approvals=approvals,
                    memories=memories,
                    user_id=user_id,
                    files=files,
                )
                try:
                    async for event in agent.run(
                        messages,
                        model=request.model,
                        effort=request.effort,
                        conversation_id=conversation_key,
                        auto_approve_tools=set(request.auto_approve_tools),
                        web_search=request.web_search,
                        research=request.research,
                        skill=request.skill,
                    ):
                        if cancel.is_set():
                            break
                        payload = event.model_dump()
                        _collect(payload, blocks, text_parts)
                        jobs.publish(conversation_key, payload)
                except asyncio.CancelledError:
                    logger.info("chat job cancelled for %s", conversation_key)
                    raise
                except Exception as exc:  # noqa: BLE001 — surface to the UI stream
                    logger.exception("chat job failed for %s", conversation_key)
                    error_payload = {"type": "error", "message": str(exc)}
                    _collect(error_payload, blocks, text_parts)
                    jobs.publish(conversation_key, error_payload)
                finally:
                    approvals.cancel_conversation(conversation_key)
                    _close_open_tools(blocks)
                    try:
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
                            "failed to persist assistant turn for %s",
                            request.conversation_id,
                        )
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("chat producer crashed for %s", conversation_key)
        finally:
            try:
                await maybe_refine_title(
                    factory=factory,
                    upstream=upstream,
                    user_id=user_id,
                    conversation_id=request.conversation_id,
                    model=request.model,
                )
            except Exception:
                logger.exception(
                    "auto-title failed for %s", request.conversation_id
                )
            jobs.publish(conversation_key, None)

    jobs.spawn(conversation_key, produce(), cancel)

    return _sse_from_job(jobs, conversation_key)


@router.post("/chat/watch", response_model=None)
async def watch_chat(
    body: WatchChatRequest,
    http_request: Request,
    user: CurrentUserDep,
) -> EventSourceResponse:
    """Reattach to an in-flight run after refresh or navigate-back."""
    factory = http_request.app.state.session_factory
    jobs: ChatJobBroker = http_request.app.state.chat_jobs
    async with factory() as session:
        try:
            await ConversationRepository(session).get(user.id, body.conversation_id)
        except UnknownConversationError as exc:
            raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc

    key = str(body.conversation_id)
    if not jobs.is_active(key):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no active run for this chat")
    return _sse_from_job(jobs, key)


@router.get("/chat/active/{conversation_id}")
async def chat_active(
    conversation_id: UUID,
    http_request: Request,
    user: CurrentUserDep,
) -> dict[str, bool]:
    """Whether a background generation is still running for this chat."""
    factory = http_request.app.state.session_factory
    jobs: ChatJobBroker = http_request.app.state.chat_jobs
    async with factory() as session:
        try:
            await ConversationRepository(session).get(user.id, conversation_id)
        except UnknownConversationError as exc:
            raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    return {"active": jobs.is_active(str(conversation_id))}


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


def _sse_from_job(jobs: ChatJobBroker, conversation_key: str) -> EventSourceResponse:
    attached = jobs.subscribe(conversation_key)
    if attached is None:

        async def empty() -> AsyncIterable[str]:
            if False:  # pragma: no cover
                yield ""

        return EventSourceResponse(empty())

    queue, replay = attached

    async def stream() -> AsyncIterable[str]:
        try:
            for payload in replay:
                yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
            while True:
                payload = await queue.get()
                if payload is None:
                    break
                yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
        except asyncio.CancelledError:
            logger.info(
                "client left stream for %s; background job continues",
                conversation_key,
            )
            return
        finally:
            jobs.unsubscribe(conversation_key, queue)

    return EventSourceResponse(
        stream(),
        headers={
            "Cache-Control": "no-cache",
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


def _close_open_tools(blocks: list[dict]) -> None:
    """Mark tools that never got a result so the UI does not spin forever."""
    for block in blocks:
        if block.get("kind") == "tool" and "result" not in block:
            block["result"] = "Error: interrupted before this finished."
            block["failed"] = True
        if block.get("kind") == "skill" and block.get("loading"):
            block["loading"] = False


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
