"""Streaming chat endpoint."""

from collections.abc import AsyncIterable

from fastapi import APIRouter
from fastapi.sse import EventSourceResponse

from agent_console.api.dependencies import AgentServiceDep
from agent_console.schemas.chat import ChatRequest

__all__ = ["router"]

router = APIRouter(prefix="/api", tags=["chat"])


@router.post("/chat", response_class=EventSourceResponse)
async def chat(request: ChatRequest, agent: AgentServiceDep) -> AsyncIterable[dict]:
    """Run the agent loop, streaming typed events as they happen.

    If the client disconnects, the generator is closed and the upstream
    connection is released by the client's context manager.
    """
    async for event in agent.run(request.messages):
        yield event.model_dump()
