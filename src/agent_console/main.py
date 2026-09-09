"""Application factory and entrypoint."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from fastapi import FastAPI

from agent_console.api.routes import chat, files, health, skills
from agent_console.clients.search import DuckDuckGoBackend, PageFetcher
from agent_console.clients.upstream import UpstreamClient
from agent_console.config import Settings, get_settings
from agent_console.repositories.files import FileRepository
from agent_console.repositories.skills import SkillRepository
from agent_console.services.tools import ToolContext, build_registry

__all__ = ["app", "create_app"]

PROJECT_ROOT = Path(__file__).resolve().parents[2]
WEB_DIR = PROJECT_ROOT / "web"


def _resolve(path: Path) -> Path:
    """Interpret relative configured paths against the project root, not the cwd."""
    return path if path.is_absolute() else PROJECT_ROOT / path


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings: Settings = app.state.settings

    skill_repository = SkillRepository(
        directories=[_resolve(d) for d in settings.skill_dirs],
        allowlist=settings.skill_allowlist,
    )
    file_repository = FileRepository(
        directory=_resolve(settings.upload_dir),
        max_bytes=settings.max_upload_bytes,
    )

    async with httpx.AsyncClient() as http_client:
        app.state.http_client = http_client
        app.state.skill_repository = skill_repository
        app.state.file_repository = file_repository
        app.state.tool_registry = build_registry(
            ToolContext(
                settings=settings,
                files=file_repository,
                skills=skill_repository,
                search=DuckDuckGoBackend(),
                pages=PageFetcher(
                    http=http_client,
                    timeout=settings.fetch_timeout,
                    max_chars=settings.max_page_chars,
                ),
            )
        )
        app.state.upstream_client = UpstreamClient(http=http_client, settings=settings)

        loaded = ", ".join(skill.name for skill in skill_repository.list()) or "none"
        print(f"skills: {loaded}")
        yield


def create_app(settings: Settings | None = None) -> FastAPI:
    app = FastAPI(title="Agent console", lifespan=lifespan)
    app.state.settings = settings or get_settings()

    app.include_router(chat.router)
    app.include_router(health.router)
    app.include_router(files.router)
    app.include_router(skills.router)

    # Low-priority route: the API paths above are matched first.
    app.frontend("/", directory=str(WEB_DIR))
    return app


app = create_app()


def run() -> None:
    import uvicorn

    settings = get_settings()
    print(f"upstream: {settings.upstream}")
    uvicorn.run(app, host="0.0.0.0", port=8000)


if __name__ == "__main__":
    run()
