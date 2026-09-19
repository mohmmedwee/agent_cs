"""Convert must not overwrite a tip that already has non-convert edits."""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

from agent_console.db.models import User
from agent_console.repositories.files import FileRepository
from agent_console.services.tools import convert_upload as convert_mod
from agent_console.services.tools.context import ToolContext
from agent_console.services.tools.registry import ToolRegistry


pytestmark = pytest.mark.db


def _registry(files: FileRepository, user: User, settings) -> ToolRegistry:
    registry = ToolRegistry()
    ctx = ToolContext(
        settings=settings,
        files=files,
        memories=MagicMock(),
        skills=MagicMock(),
        search=MagicMock(),
        pages=MagicMock(),
        cache=MagicMock(),
        user_id=user.id,
        upstream=MagicMock(),
    )
    convert_mod.register(registry, ctx)
    return registry


@pytest.fixture
def settings():
    from agent_console.config import get_settings

    return get_settings()


async def test_second_convert_allowed_when_tip_still_from_same_markdown(
    files: FileRepository, user: User, settings
) -> None:
    await files.save(
        user.id,
        name="guard.md",
        data=b"# Doc\n\nOwner: Alice\n",
        content_type="text/markdown",
    )
    registry = _registry(files, user, settings)
    out1 = await registry.invoke(
        "convert_upload_to_docx",
        json.dumps(
            {
                "source": "guard.md",
                "theme": "cleverso",
                "replacements": [{"find": "Owner: Alice", "replace": "Owner: Carol"}],
            }
        ),
    )
    assert out1.startswith("Converted")
    # Second convert reloads the original markdown (still Alice), not the tip.
    out2 = await registry.invoke(
        "convert_upload_to_docx",
        json.dumps(
            {
                "source": "guard.md",
                "theme": "cleverso",
                "replacements": [{"find": "Owner: Alice", "replace": "Owner: Bob"}],
            }
        ),
    )
    assert out2.startswith("Converted"), out2
    tip = await files.latest_in_chain(user.id, "guard.docx")
    assert tip.version == 2


async def test_convert_refuses_when_tip_was_edited_off_markdown(
    files: FileRepository, user: User, settings
) -> None:
    md = await files.save(
        user.id,
        name="guard2.md",
        data=b"# Doc\n\nOwner: Alice\n",
        content_type="text/markdown",
    )
    registry = _registry(files, user, settings)
    out1 = await registry.invoke(
        "convert_upload_to_docx",
        json.dumps({"source": "guard2.md", "theme": "cleverso"}),
    )
    assert out1.startswith("Converted")
    tip = await files.latest_in_chain(user.id, "guard2.docx")
    body = await files.raw_bytes(user.id, str(tip.id))
    await files.save(
        user.id,
        name="guard2.docx",
        data=body + b"|EDIT",
        parent_id=tip.id,
        derived_from=tip.id,
    )
    out2 = await registry.invoke(
        "convert_upload_to_docx",
        json.dumps(
            {
                "source": "guard2.md",
                "theme": "cleverso",
                "replacements": [{"find": "Owner: Alice", "replace": "Owner: Bob"}],
            }
        ),
    )
    assert out2.startswith("Error:")
    tip2 = await files.latest_in_chain(user.id, "guard2.docx")
    assert tip2.version == 2
    assert (await files.raw_bytes(user.id, str(tip2.id))).endswith(b"|EDIT")
    assert tip.derived_from == md.id


async def test_convert_refuses_after_edit_even_if_derived_from_copied_from_md(
    files: FileRepository, user: User, settings
) -> None:
    """md → convert → edit → reconvert must error; derived_from=md is rejected."""
    from agent_console.repositories.files import InvalidDerivedFromError

    md = await files.save(
        user.id,
        name="guard3.md",
        data=b"# Doc\n\nOwner: Alice\n",
        content_type="text/markdown",
    )
    registry = _registry(files, user, settings)
    out1 = await registry.invoke(
        "convert_upload_to_docx",
        json.dumps({"source": "guard3.md", "theme": "cleverso"}),
    )
    assert out1.startswith("Converted")
    tip = await files.latest_in_chain(user.id, "guard3.docx")
    body = await files.raw_bytes(user.id, str(tip.id))

    with pytest.raises(InvalidDerivedFromError, match="cannot set derived_from"):
        await files.save(
            user.id,
            name="guard3.docx",
            data=body + b"|EDIT",
            parent_id=tip.id,
            derived_from=md.id,
        )

    # Legitimate tip edit uses parent tip as provenance, not the markdown.
    await files.save(
        user.id,
        name="guard3.docx",
        data=body + b"|EDIT",
        parent_id=tip.id,
        derived_from=tip.id,
    )
    out2 = await registry.invoke(
        "convert_upload_to_docx",
        json.dumps({"source": "guard3.md", "theme": "cleverso"}),
    )
    assert out2.startswith("Error:"), out2
    tip2 = await files.latest_in_chain(user.id, "guard3.docx")
    assert tip2.version == 2
    assert (await files.raw_bytes(user.id, str(tip2.id))).endswith(b"|EDIT")
