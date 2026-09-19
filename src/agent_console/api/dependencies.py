"""Dependency wiring for the API layer.

Two lifetimes are in play. Things that are expensive and stateless — the HTTP
pool, the resolved-model cache, the skill index, the Redis connection — are
built once at startup and shared. Things scoped to a caller — the database
session, repositories, the tool registry — are built per request, because they
carry the current user's identity and that is what keeps accounts separated.
"""

import asyncio
from collections.abc import AsyncIterator
from contextlib import suppress
from typing import Annotated

from fastapi import Depends, HTTPException, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from agent_console.clients.cache import ResponseCache
from agent_console.clients.search import PageFetcher
from agent_console.clients.upstream import UpstreamClient
from agent_console.config import Settings
from agent_console.db.models import User
from agent_console.repositories.conversations import ConversationRepository
from agent_console.repositories.files import FileRepository
from agent_console.repositories.memory import MemoryRepository
from agent_console.repositories.skill_catalog import SkillCatalog
from agent_console.repositories.skills import SkillRepository
from agent_console.repositories.user_skills import UserSkillRepository
from agent_console.repositories.users import UserRepository
from agent_console.services.agent import AgentService
from agent_console.services.approvals import ApprovalBroker
from agent_console.services.security import PasswordHasherService, SessionTokenService
from agent_console.services.tools import ToolContext, ToolRegistry, build_registry

__all__ = [
    "AdminDep",
    "AgentServiceDep",
    "ApprovalBrokerDep",
    "ConversationRepositoryDep",
    "CurrentUserDep",
    "DbSessionDep",
    "FileRepositoryDep",
    "MemoryRepositoryDep",
    "PasswordHasherDep",
    "SessionTokenDep",
    "SettingsDep",
    "SkillCatalogDep",
    "SkillRepositoryDep",
    "ToolRegistryDep",
    "UpstreamClientDep",
    "UserRepositoryDep",
    "UserSkillRepositoryDep",
    "SESSION_COOKIE",
    "set_session_cookie",
    "clear_session_cookie",
]

SESSION_COOKIE = "agent_console_session"


# --- startup-scoped singletons ------------------------------------------

def _settings(request: Request) -> Settings:
    return request.app.state.settings


def _upstream_client(request: Request) -> UpstreamClient:
    return request.app.state.upstream_client


def _skill_repository(request: Request) -> SkillRepository:
    return request.app.state.skill_repository


def _cache(request: Request) -> ResponseCache:
    return request.app.state.cache


def _password_hasher(request: Request) -> PasswordHasherService:
    return request.app.state.password_hasher


def _session_tokens(request: Request) -> SessionTokenService:
    return request.app.state.session_tokens


# --- request-scoped ------------------------------------------------------

async def _db_session(request: Request) -> AsyncIterator[AsyncSession]:
    """One session per request.

    Client disconnects (and React Query aborting a superseded fetch) cancel the
    request task while the pool is still closing its connection. That used to
    surface as a scary `Exception terminating connection` / `CancelledError`
    traceback even though the response had already returned 200. Closing here
    ourselves, and invalidating on cancel, keeps the pool quiet and healthy.
    """
    factory = request.app.state.session_factory
    session = factory()
    try:
        yield session
    except Exception:
        await session.rollback()
        raise
    except BaseException:
        # CancelledError is a BaseException: still roll back so a half-finished
        # transaction is never returned to the pool.
        with suppress(Exception):
            await session.rollback()
        raise
    else:
        await session.commit()
    finally:
        try:
            await session.close()
        except asyncio.CancelledError:
            with suppress(Exception):
                await session.invalidate()
            raise


DbSessionDep = Annotated[AsyncSession, Depends(_db_session)]
SettingsDep = Annotated[Settings, Depends(_settings)]
UpstreamClientDep = Annotated[UpstreamClient, Depends(_upstream_client)]
SkillRepositoryDep = Annotated[SkillRepository, Depends(_skill_repository)]
CacheDep = Annotated[ResponseCache, Depends(_cache)]
PasswordHasherDep = Annotated[PasswordHasherService, Depends(_password_hasher)]
SessionTokenDep = Annotated[SessionTokenService, Depends(_session_tokens)]


def _user_repository(session: DbSessionDep) -> UserRepository:
    return UserRepository(session)


UserRepositoryDep = Annotated[UserRepository, Depends(_user_repository)]


async def _current_user(
    session: DbSessionDep,
    settings: SettingsDep,
    tokens: SessionTokenDep,
    request: Request,
) -> User:
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "not signed in")

    user_id = tokens.read(token)
    if not user_id:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "session expired")

    user = await UserRepository(session).by_id(user_id)
    if user is None or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "account unavailable")
    return user


CurrentUserDep = Annotated[User, Depends(_current_user)]


async def _admin(user: CurrentUserDep) -> User:
    if not user.is_admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "admin only")
    return user


AdminDep = Annotated[User, Depends(_admin)]


def _file_repository(request: Request, session: DbSessionDep, settings: SettingsDep) -> FileRepository:
    return FileRepository(
        session, request.app.state.blob_store, settings.max_upload_bytes
    )


def _memory_repository(session: DbSessionDep, settings: SettingsDep) -> MemoryRepository:
    return MemoryRepository(
        session,
        max_items=settings.max_memory_items,
        max_chars=settings.max_memory_chars,
    )


def _user_skill_repository(
    session: DbSessionDep,
    settings: SettingsDep,
    builtins: SkillRepositoryDep,
) -> UserSkillRepository:
    return UserSkillRepository(
        session,
        max_items=settings.max_user_skills,
        max_body_chars=settings.max_user_skill_body_chars,
        reserved_names=builtins.names(),
    )


def _conversation_repository(session: DbSessionDep) -> ConversationRepository:
    return ConversationRepository(session)


FileRepositoryDep = Annotated[FileRepository, Depends(_file_repository)]
MemoryRepositoryDep = Annotated[MemoryRepository, Depends(_memory_repository)]
UserSkillRepositoryDep = Annotated[
    UserSkillRepository, Depends(_user_skill_repository)
]
ConversationRepositoryDep = Annotated[
    ConversationRepository, Depends(_conversation_repository)
]


async def _skill_catalog(
    builtins: SkillRepositoryDep,
    user_skills: UserSkillRepositoryDep,
    user: CurrentUserDep,
) -> SkillCatalog:
    rows = await user_skills.list_enabled(user.id)
    return SkillCatalog(builtins, rows)


SkillCatalogDep = Annotated[SkillCatalog, Depends(_skill_catalog)]


def _tool_registry(
    request: Request,
    settings: SettingsDep,
    files: FileRepositoryDep,
    memories: MemoryRepositoryDep,
    skills: SkillCatalogDep,
    cache: CacheDep,
    user: CurrentUserDep,
    upstream: UpstreamClientDep,
) -> ToolRegistry:
    """Built per request so every file tool is bound to this user."""
    state = request.app.state
    return build_registry(
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
            cache=cache,
            user_id=user.id,
            upstream=upstream,
        )
    )


ToolRegistryDep = Annotated[ToolRegistry, Depends(_tool_registry)]


def _approvals(request: Request) -> ApprovalBroker:
    return request.app.state.approvals


ApprovalBrokerDep = Annotated[ApprovalBroker, Depends(_approvals)]


def _agent_service(
    upstream: UpstreamClientDep,
    tools: ToolRegistryDep,
    settings: SettingsDep,
    skills: SkillCatalogDep,
    approvals: ApprovalBrokerDep,
    memories: MemoryRepositoryDep,
    files: FileRepositoryDep,
    user: CurrentUserDep,
) -> AgentService:
    return AgentService(
        upstream=upstream,
        tools=tools,
        settings=settings,
        skills=skills,
        approvals=approvals,
        memories=memories,
        user_id=user.id,
        files=files,
    )


AgentServiceDep = Annotated[AgentService, Depends(_agent_service)]


# --- cookie helpers -------------------------------------------------------

def set_session_cookie(response: Response, token: str, settings: Settings) -> None:
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=settings.session_ttl,
        httponly=True,  # unreadable from JavaScript, so XSS cannot lift it
        samesite="lax",
        secure=settings.cookie_secure,
        path="/",
    )


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(SESSION_COOKIE, path="/")
