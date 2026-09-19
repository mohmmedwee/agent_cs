"""QW1: linear file version chains (TDD — these fail until lineage lands)."""

from __future__ import annotations

import pytest
from sqlalchemy.exc import IntegrityError

from agent_console.db.models import User
from agent_console.repositories.files import FileRepository


pytestmark = pytest.mark.db


async def test_edit_chain_a_to_b_to_c_keeps_both_changes(
    files: FileRepository, user: User
) -> None:
    """Second edit must start from tip B, not original A — both markers survive."""
    a = await files.save(user.id, name="report.docx", data=b"ROOT")
    b = await files.save(
        user.id,
        name="report.docx",
        data=(await files.raw_bytes(user.id, str(a.id))) + b"|EDIT_B",
        parent_id=a.id,
    )
    tip = await files.latest_in_chain(user.id, str(a.id))
    assert tip.id == b.id

    c = await files.save(
        user.id,
        name="report.docx",
        data=(await files.raw_bytes(user.id, str(tip.id))) + b"|EDIT_C",
        parent_id=tip.id,
    )
    tip2 = await files.latest_in_chain(user.id, str(a.id))
    assert tip2.id == c.id
    body = await files.raw_bytes(user.id, str(tip2.id))
    assert body == b"ROOT|EDIT_B|EDIT_C"
    assert c.parent_id == b.id
    assert c.root_id == a.id
    assert c.version == 3


async def test_concurrent_child_of_same_parent_rejected(
    files: FileRepository, user: User, blob_dir
) -> None:
    """Two saves parenting the same tip must not both succeed (CAS / unique parent).

    The losing save must not leave an orphaned blob on disk.
    """
    a = await files.save(user.id, name="doc.docx", data=b"A")
    await files.save(user.id, name="doc.docx", data=b"B1", parent_id=a.id)
    before = {p.name for p in blob_dir.iterdir()}
    with pytest.raises(IntegrityError):
        await files.save(user.id, name="doc.docx", data=b"B2", parent_id=a.id)
    after = {p.name for p in blob_dir.iterdir()}
    assert after == before


async def test_name_resolves_to_chain_tip(
    files: FileRepository, user: User
) -> None:
    a = await files.save(user.id, name="named.docx", data=b"A")
    b = await files.save(
        user.id, name="named.docx", data=b"B", parent_id=a.id
    )
    got = await files.get(user.id, "named.docx")
    assert got.id == b.id
    tip = await files.latest_in_chain(user.id, "named.docx")
    assert tip.id == b.id
