"""Shared fixtures. Pure-logic tests need none of these."""

from __future__ import annotations

import os
import shutil
from collections.abc import AsyncIterator
from pathlib import Path
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from agent_console.db.base import Base
import agent_console.db.models  # noqa: F401 — register tables
from agent_console.db.models import User
from agent_console.repositories.files import FileRepository
from agent_console.storage.blob_store import LocalBlobStore


def pytest_collection_modifyitems(config, items):  # noqa: ARG001
    has_db = bool(os.environ.get("TEST_DATABASE_URL"))
    has_soffice = shutil.which("soffice") is not None
    for item in items:
        if "db" in item.keywords and not has_db:
            item.add_marker(pytest.mark.skip(reason="TEST_DATABASE_URL not set"))
        if "soffice" in item.keywords and not has_soffice:
            item.add_marker(pytest.mark.skip(reason="LibreOffice not installed"))


@pytest_asyncio.fixture
async def session() -> AsyncIterator[AsyncSession]:
    url = os.environ["TEST_DATABASE_URL"]
    engine = create_async_engine(url)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        yield s
        await s.rollback()
    await engine.dispose()


@pytest_asyncio.fixture
async def user(session: AsyncSession) -> User:
    row = User(
        email=f"test-{uuid4().hex[:10]}@example.com",
        display_name="Tester",
        password_hash="unused",
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return row


@pytest.fixture
def blob_dir(tmp_path: Path) -> Path:
    return tmp_path / "blobs"


@pytest_asyncio.fixture
async def files(session: AsyncSession, blob_dir: Path) -> FileRepository:
    return FileRepository(session, LocalBlobStore(blob_dir), max_bytes=10 * 1024 * 1024)
