"""Compress long chat transcripts before they blow the model context window.

Not a tool — runs in the chat path when estimated tokens cross a fraction of
`context_window`. Older turns become a rolling summary; recent turns stay raw.
The full UI transcript is unchanged.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from agent_console.clients.upstream import UpstreamClient, UpstreamError
from agent_console.config import Settings
from agent_console.db.models import Conversation

__all__ = [
    "CONTEXT_OVERHEAD_TOKENS",
    "estimate_tokens",
    "estimate_message_tokens",
    "prepare_model_messages",
]

logger = logging.getLogger(__name__)

# Rough stand-in for system prompt + skill index + tool schemas.
CONTEXT_OVERHEAD_TOKENS = 2_500


def estimate_tokens(text: str) -> int:
    """Approximate tokens; matches the frontend meter well enough to trigger."""
    if not text:
        return 0
    tokens = 0.0
    for char in text:
        code = ord(char)
        if (
            0x0600 <= code <= 0x06FF
            or 0x0750 <= code <= 0x077F
            or 0x4E00 <= code <= 0x9FFF
            or 0x3400 <= code <= 0x4DBF
        ):
            tokens += 0.6
        else:
            tokens += 0.25
    return max(1, int(tokens + 0.999))


def estimate_message_tokens(messages: list[dict[str, Any]]) -> int:
    total = 0
    for message in messages:
        content = message.get("content") or ""
        if isinstance(content, str):
            total += estimate_tokens(content)
        total += 4  # role framing
    return total


def _format_turns(messages: list[dict[str, str]]) -> str:
    lines: list[str] = []
    for message in messages:
        role = message.get("role", "user").upper()
        content = (message.get("content") or "").strip()
        if not content:
            continue
        # Cap each turn so one giant write_file dump cannot dominate the fold.
        if len(content) > 2_000:
            content = content[:2_000] + "…"
        lines.append(f"{role}: {content}")
    return "\n\n".join(lines)


async def _summarize(
    *,
    upstream: UpstreamClient,
    model: str,
    prior_summary: str | None,
    turns: list[dict[str, str]],
) -> str:
    prior = prior_summary or "(none yet)"
    body_turns = _format_turns(turns)
    prompt = (
        "You compress chat history for a continuing assistant. "
        "Write a concise rolling summary the assistant will use instead of "
        "the raw older turns.\n\n"
        "Rules:\n"
        "- Keep decisions, constraints, names, file names, and open questions.\n"
        "- Drop greetings, filler, and repeated tool noise.\n"
        "- Prefer bullet points. Max ~400 words.\n"
        "- Do not invent facts that are not in the material.\n\n"
        f"Existing summary:\n{prior}\n\n"
        f"New turns to fold in:\n{body_turns}\n\n"
        "Updated summary:"
    )
    return await upstream.complete_text(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.2,
        max_tokens=1_200,
    )


async def prepare_model_messages(
    *,
    conversation: Conversation,
    transcript: list[dict[str, str]],
    settings: Settings,
    upstream: UpstreamClient,
    model: str | None,
) -> list[dict[str, str]]:
    """Return the message list the agent loop should see.

    May update `conversation.context_summary` / `summarized_count` in place
    (caller commits). On summarizer failure, falls back to the full transcript.
    """
    covered = max(0, min(conversation.summarized_count, len(transcript)))
    summary = (conversation.context_summary or "").strip() or None
    remainder = transcript[covered:]

    budget = int(settings.context_window * settings.context_summarize_ratio)
    keep = settings.context_keep_recent

    def build(
        summary_text: str | None, recent: list[dict[str, str]]
    ) -> list[dict[str, str]]:
        out: list[dict[str, str]] = []
        if summary_text:
            # Use `user`, not `system`: the agent already prepends the real
            # system prompt. A second system role (or any system after turn 1)
            # breaks Qwen chat templates ("System message must be at the
            # beginning").
            out.append(
                {
                    "role": "user",
                    "content": (
                        "Earlier in this conversation (compressed for length):\n\n"
                        f"{summary_text}"
                    ),
                }
            )
            out.append(
                {
                    "role": "assistant",
                    "content": "Understood — I'll use that summary as prior context.",
                }
            )
        out.extend(recent)
        return out

    candidate = build(summary, remainder)
    used = CONTEXT_OVERHEAD_TOKENS + estimate_message_tokens(candidate)

    over_tokens = used > budget
    over_length = len(remainder) > max(keep, settings.context_summarize_after_messages)
    if (not over_tokens and not over_length) or len(remainder) <= keep:
        return candidate

    fold = remainder[:-keep] if keep < len(remainder) else remainder[:-1]
    recent = remainder[len(fold) :]
    if not fold:
        return candidate

    try:
        chosen = model or await upstream.resolve_model()
        new_summary = await _summarize(
            upstream=upstream,
            model=chosen,
            prior_summary=summary,
            turns=fold,
        )
    except (UpstreamError, httpx.HTTPError, KeyError) as exc:
        logger.warning("context summarization failed; sending full remainder: %s", exc)
        return candidate

    conversation.context_summary = new_summary
    conversation.summarized_count = covered + len(fold)
    logger.info(
        "summarized %d turns for conversation %s (through count=%d)",
        len(fold),
        conversation.id,
        conversation.summarized_count,
    )
    return build(new_summary, recent)
