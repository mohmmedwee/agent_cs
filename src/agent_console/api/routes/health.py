"""Upstream reachability check, surfaced in the UI header."""

from __future__ import annotations

import subprocess
from functools import lru_cache
from pathlib import Path

from fastapi import APIRouter

from agent_console.api.dependencies import SettingsDep, UpstreamClientDep
from agent_console.schemas.health import HealthResponse

__all__ = ["router"]

router = APIRouter(prefix="/api", tags=["health"])

_REPO_ROOT = Path(__file__).resolve().parents[4]


@lru_cache(maxsize=1)
def _git_head() -> str | None:
    """Short HEAD SHA — stable for the process lifetime."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=_REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    rev = result.stdout.strip()
    return rev or None


def _git_dirty() -> bool:
    """True when the working tree has uncommitted changes (checked each call)."""
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=_REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0 and bool(result.stdout.strip())


def _git_revision() -> str | None:
    """HEAD short SHA, with ``-dirty`` when the tree does not match the commit."""
    head = _git_head()
    if head is None:
        return None
    return f"{head}-dirty" if _git_dirty() else head


@router.get("/health")
async def health(upstream: UpstreamClientDep, settings: SettingsDep) -> HealthResponse:
    revision = _git_revision()
    try:
        model = await upstream.resolve_model()
    except Exception as exc:
        return HealthResponse(
            upstream=settings.upstream,
            ok=False,
            error=str(exc),
            context_window=settings.context_window,
            revision=revision,
        )
    return HealthResponse(
        upstream=settings.upstream,
        ok=True,
        model=model,
        context_window=settings.context_window,
        revision=revision,
    )
