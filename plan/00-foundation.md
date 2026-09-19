# 00 — Foundation (do this once, before F1)

Every feature spec below ends with tests. The repo has **no test setup today** (no `tests/`, no pytest in
`pyproject.toml`, no vitest in `frontend/package.json`). Set it up first. It takes about an hour.

## Step 1: backend test tooling

`pyproject.toml`: add a dev dependency group and pytest config:

```toml
[dependency-groups]
dev = [
  "pytest>=8.3",
  "pytest-asyncio>=0.24",
]

[tool.pytest.ini_options]
testpaths = ["tests"]
asyncio_mode = "auto"
markers = [
  "db: needs a running Postgres (DATABASE_URL); skipped otherwise",
  "soffice: needs LibreOffice on PATH; skipped otherwise",
]
```

Install: `uv sync --group dev` (the repo already has `uv.lock`).

## Step 2: `tests/conftest.py`

```python
"""Shared fixtures. Pure-logic tests need none of these."""

import os
import shutil

import pytest


def pytest_collection_modifyitems(config, items):
    has_db = bool(os.environ.get("TEST_DATABASE_URL"))
    has_soffice = shutil.which("soffice") is not None
    for item in items:
        if "db" in item.keywords and not has_db:
            item.add_marker(pytest.mark.skip(reason="TEST_DATABASE_URL not set"))
        if "soffice" in item.keywords and not has_soffice:
            item.add_marker(pytest.mark.skip(reason="LibreOffice not installed"))
```

DB-backed tests (`@pytest.mark.db`) use a **separate** database named in `TEST_DATABASE_URL`, e.g.
`postgresql+asyncpg://postgres:postgres@127.0.0.1:5432/agent_console_test`. A fixture creates the schema with
`Base.metadata.create_all` in a transaction and rolls it back per test:

```python
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from agent_console.db.base import Base
import agent_console.db.models  # noqa: F401  (register tables)


@pytest_asyncio.fixture
async def session():
    engine = create_async_engine(os.environ["TEST_DATABASE_URL"])
    async with engine.connect() as conn:
        await conn.run_sync(Base.metadata.create_all)
        trans = await conn.begin()
        async with AsyncSession(bind=conn, expire_on_commit=False) as s:
            yield s
        await trans.rollback()
    await engine.dispose()
```

A `user` fixture inserts a `User` row and returns it.

## Step 3: frontend test tooling

```bash
cd frontend && npm i -D vitest@^3
```

`package.json` scripts: `"test": "vitest run"`. Add to `vite.config.ts`:

```ts
test: { environment: 'node', include: ['src/**/*.test.ts'] },
```

(`/// <reference types="vitest/config" />` at the top of `vite.config.ts` so `test` type-checks.)

Put tests next to the helper: `src/lib/groupConversations.test.ts` and so on. Write one for the existing
`groupConversations` now to prove the setup works.

## Step 4: the check command

Add a `scripts/check.sh` that every feature runs before it's called done:

```bash
#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
ruff check src tests
pytest -q
(cd frontend && npm run build && npm run lint && npm test)
```

## Done when
- [ ] `pytest -q` runs (0 tests is fine at this point) and the DB/soffice markers skip cleanly.
- [ ] `cd frontend && npm test` runs the `groupConversations` test green.
- [ ] `scripts/check.sh` passes on the current `master`.
