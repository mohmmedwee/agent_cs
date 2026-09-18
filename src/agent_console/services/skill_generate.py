"""Draft a user skill via the installed `skill-creator` skill + the model."""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path

import httpx

from agent_console.clients.upstream import UpstreamClient, UpstreamError
from agent_console.repositories.skills import SkillRepository
from agent_console.repositories.user_skills import slugify_skill_name

__all__ = ["SkillDraft", "generate_skill_draft", "SkillGenerateError"]

logger = logging.getLogger(__name__)

_JSON_FENCE = re.compile(r"```(?:json)?\s*([\s\S]*?)```", re.IGNORECASE)
_SKILL_NAME = "skill-creator"
_FALLBACK_CREATOR = Path(__file__).resolve().parents[3] / "skills" / "skill-creator" / "SKILL.md"

_OUTPUT_CONTRACT = (
    "\n\n---\n"
    "Now draft ONE skill for the user's request below. "
    "Follow the skill-creator rules above. "
    "Reply with ONLY the JSON object (name, description, body) — "
    "no markdown fences, no preamble."
)


class SkillGenerateError(RuntimeError):
    """The model did not return a usable skill draft."""


class SkillDraft(dict):
    """Typed-ish mapping: name, description, body."""


def _load_creator_body(builtins: SkillRepository | None) -> str:
    """Prefer the live skill-creator from the skill index; else the project file."""
    if builtins is not None:
        try:
            return builtins.read(_SKILL_NAME, max_chars=12_000)
        except Exception:  # noqa: BLE001 — fall through to disk
            logger.info("skill-creator not in index; reading from disk")
    if _FALLBACK_CREATOR.is_file():
        text = _FALLBACK_CREATOR.read_text(encoding="utf-8")
        # Strip YAML frontmatter for the model prompt.
        if text.startswith("---"):
            _, _, rest = text.partition("\n---")
            return rest.lstrip("\n")
        return text
    raise SkillGenerateError(
        "skill-creator is not installed — add skills/skill-creator/SKILL.md"
    )


def _parse_draft(raw: str) -> dict[str, str]:
    text = raw.strip()
    fence = _JSON_FENCE.search(text)
    if fence:
        text = fence.group(1).strip()
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end <= start:
        raise SkillGenerateError("model reply was not JSON")
    try:
        data = json.loads(text[start : end + 1])
    except json.JSONDecodeError as exc:
        raise SkillGenerateError("model reply was not valid JSON") from exc
    if not isinstance(data, dict):
        raise SkillGenerateError("model reply was not a JSON object")

    name = slugify_skill_name(str(data.get("name") or ""))
    description = " ".join(str(data.get("description") or "").split()).strip()
    body = str(data.get("body") or "").strip()
    if not name or not description or not body:
        raise SkillGenerateError("model omitted name, description, or body")
    if len(description) > 500:
        description = description[:497].rstrip() + "…"
    return {"name": name, "description": description, "body": body}


async def generate_skill_draft(
    *,
    upstream: UpstreamClient,
    prompt: str,
    model: str | None = None,
    builtins: SkillRepository | None = None,
) -> dict[str, str]:
    """Ask the model to draft a skill, guided by skill-creator."""
    idea = prompt.strip()
    if len(idea) < 3:
        raise SkillGenerateError("describe the skill in a few words first")

    creator = _load_creator_body(builtins)
    system = creator + _OUTPUT_CONTRACT

    chosen = model or await upstream.resolve_model()
    try:
        raw = await upstream.complete_text(
            model=chosen,
            messages=[
                {"role": "system", "content": system},
                {
                    "role": "user",
                    "content": f"User request:\n\n{idea[:2000]}",
                },
            ],
            temperature=0.3,
            max_tokens=1_400,
            effort="minimal",
            timeout=60.0,
        )
    except (UpstreamError, httpx.HTTPError, TimeoutError) as exc:
        logger.info("skill generate failed: %s", exc)
        raise SkillGenerateError(
            "could not reach the model in time — try again, or write the skill yourself"
        ) from exc

    return _parse_draft(raw)
