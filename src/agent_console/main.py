"""Application factory and entrypoint."""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from fastapi import FastAPI
from redis.asyncio import Redis

from agent_console.api.routes import admin, auth, chat, conversations, files, health, skills
from agent_console.clients.cache import ResponseCache
from agent_console.clients.search import DuckDuckGoBackend
from agent_console.clients.upstream import UpstreamClient
from agent_console.config import Settings, get_settings
from agent_console.db.session import build_engine, build_session_factory
from agent_console.repositories.skills import SkillRepository
from agent_console.services.security import PasswordHasherService, SessionTokenService

__all__ = ["app", "create_app"]

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
WEB_DIR = PROJECT_ROOT / "web" / "dist"


def _resolve(path: Path) -> Path:
    """Interpret relative configured paths against the project root, not the cwd."""
    return path if path.is_absolute() else PROJECT_ROOT / path


async def _connect_redis(settings: Settings) -> Redis | None:
    """Redis is a cache, so a failure to reach it degrades rather than fatal."""
    client = Redis.from_url(settings.redis_url)
    try:
        await client.ping()
    except Exception as exc:  # noqa: BLE001
        logger.warning("redis unavailable (%s); running without cache", exc)
        await client.aclose()
        return None
    return client


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Build everything that outlives a single request.

    Per-user collaborators are deliberately absent here — repositories and the
    tool registry are constructed per request in `api.dependencies`, because
    they carry the caller's identity.
    """
    settings: Settings = app.state.settings

    engine = build_engine(settings.database_url, echo=settings.database_echo)
    redis = await _connect_redis(settings)

    upload_dir = _resolve(settings.upload_dir)
    upload_dir.mkdir(parents=True, exist_ok=True)

    async with httpx.AsyncClient() as http_client:
        app.state.http_client = http_client
        app.state.engine = engine
        app.state.session_factory = build_session_factory(engine)
        app.state.cache = ResponseCache(redis, settings.redis_prefix)
        app.state.search_backend = DuckDuckGoBackend()
        app.state.upstream_client = UpstreamClient(http=http_client, settings=settings)
        app.state.password_hasher = PasswordHasherService()
        app.state.session_tokens = SessionTokenService(
            secret=settings.secret_key, max_age_seconds=settings.session_ttl
        )
        app.state.skill_repository = SkillRepository(
            directories=[_resolve(d) for d in settings.skill_dirs],
            allowlist=settings.skill_allowlist,
        )

        count = len(app.state.skill_repository.list())
        logger.info("loaded %d skills; upstream %s", count, settings.upstream)

        try:
            yield
        finally:
            if redis is not None:
                await redis.aclose()
            await engine.dispose()


def create_app(settings: Settings | None = None) -> FastAPI:
    app = FastAPI(title="Agent console", lifespan=lifespan)
    app.state.settings = settings or get_settings()

    app.include_router(auth.router)
    app.include_router(conversations.router)
    app.include_router(chat.router)
    app.include_router(health.router)
    app.include_router(files.router)
    app.include_router(skills.router)
    app.include_router(admin.router)

    # Low-priority route: the API paths above are matched first. Unknown paths
    # fall through to index.html so client-side routes survive a page reload.
    if WEB_DIR.exists():
        app.frontend("/", directory=str(WEB_DIR))
    return app


app = create_app()


def run() -> None:
    import uvicorn

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    uvicorn.run(app, host="0.0.0.0", port=8000)


if __name__ == "__main__":
    run()
