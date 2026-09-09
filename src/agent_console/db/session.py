"""Async engine and session factory."""

import asyncio
from collections.abc import AsyncIterator
from contextlib import suppress

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

__all__ = ["build_engine", "build_session_factory", "session_scope"]


def build_engine(url: str, echo: bool = False) -> AsyncEngine:
    return create_async_engine(
        url,
        echo=echo,
        pool_pre_ping=True,  # the Postgres container may outlive our idle pool
        pool_size=5,
        max_overflow=10,
    )


def build_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


async def session_scope(
    factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[AsyncSession]:
    """One session per request, committed on success and rolled back on error."""
    session = factory()
    try:
        yield session
    except Exception:
        await session.rollback()
        raise
    except BaseException:
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
