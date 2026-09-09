"""Upstream reachability check, surfaced in the UI header."""

from fastapi import APIRouter

from agent_console.api.dependencies import SettingsDep, UpstreamClientDep
from agent_console.schemas.health import HealthResponse

__all__ = ["router"]

router = APIRouter(prefix="/api", tags=["health"])


@router.get("/health")
async def health(upstream: UpstreamClientDep, settings: SettingsDep) -> HealthResponse:
    try:
        model = await upstream.resolve_model()
    except Exception as exc:
        return HealthResponse(
            upstream=settings.upstream,
            ok=False,
            error=str(exc),
            context_window=settings.context_window,
        )
    return HealthResponse(
        upstream=settings.upstream,
        ok=True,
        model=model,
        context_window=settings.context_window,
    )
