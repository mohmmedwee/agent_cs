"""Refine a conversation title after the first exchange."""

from __future__ import annotations

import logging
import re
from uuid import UUID

import httpx
from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession

from agent_console.clients.upstream import UpstreamClient, UpstreamError
from agent_console.repositories.conversations import ConversationRepository, title_from

__all__ = ["maybe_refine_title"]

logger = logging.getLogger(__name__)

_TITLE_MAX = 60


def _clean_title(raw: str) -> str:
    line = raw.strip().split("\n", 1)[0]
    line = re.sub(r'^["“\'«]+|["”\'»]+$', "", line).strip()
    line = re.sub(r"^(title|عنوان)\s*:\s*", "", line, flags=re.IGNORECASE).strip()
    if len(line) > _TITLE_MAX:
        line = f"{line[:_TITLE_MAX].rstrip()}…"
    return line or "New chat"


async def maybe_refine_title(
    *,
    factory: async_sessionmaker[AsyncSession],
    upstream: UpstreamClient,
    user_id: UUID,
    conversation_id: UUID,
    model: str | None,
) -> None:
    """Replace the first-line stub title with a short model title (best-effort)."""
    async with factory() as session:
        conversations = ConversationRepository(session)
        conversation = await conversations.get(user_id, conversation_id)
        messages = [m for m in conversation.messages if m.content]
        if len(messages) != 2:
            return
        if messages[0].role != "user" or messages[1].role != "assistant":
            return

        user_text = messages[0].content
        assistant_text = messages[1].content
        stub = title_from(user_text)
        if conversation.title not in ("", "New chat", stub):
            # User already renamed it.
            return

        prompt = (
            "Write a short chat title (max 6 words) for this conversation. "
            "Match the user's language. No quotes, no trailing punctuation, "
            "no prefix like Title:.\n\n"
            f"User: {user_text[:500]}\n\n"
            f"Assistant: {assistant_text[:500]}\n\n"
            "Title:"
        )
        try:
            chosen = model or await upstream.resolve_model()
            raw = await upstream.complete_text(
                model=chosen,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=40,
            )
        except (UpstreamError, httpx.HTTPError, KeyError) as exc:
            logger.info("auto-title skipped for %s: %s", conversation_id, exc)
            return

        title = _clean_title(raw)
        if title in ("New chat", stub) or len(title) < 2:
            return
        await conversations.rename(user_id, conversation_id, title)
        await session.commit()
        logger.info("auto-titled conversation %s → %s", conversation_id, title)
