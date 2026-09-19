"""Shared fixtures. Pure-logic tests need none of these."""

from __future__ import annotations

import os
import shutil

import pytest


def pytest_collection_modifyitems(config, items):  # noqa: ARG001
    has_db = bool(os.environ.get("TEST_DATABASE_URL"))
    has_soffice = shutil.which("soffice") is not None
    for item in items:
        if "db" in item.keywords and not has_db:
            item.add_marker(pytest.mark.skip(reason="TEST_DATABASE_URL not set"))
        if "soffice" in item.keywords and not has_soffice:
            item.add_marker(pytest.mark.skip(reason="LibreOffice not installed"))
