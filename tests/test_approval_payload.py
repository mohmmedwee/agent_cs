"""ApprovalBroker stores only plain JSON payloads (Redis-ready)."""

from __future__ import annotations

import asyncio

import pytest

from agent_console.services.approvals import ApprovalBroker, _as_json_dict


def test_payload_roundtrip_keeps_ops_diff_and_ids() -> None:
    payload = {
        "source_file_id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
        "generation": 1,
        "hashes": {"g1:p_0001": "a1b2c3d4"},
        "operations": [
            {
                "op": "replace",
                "block_id": "g1:p_0001",
                "old": "45 days",
                "new": "30 days",
            }
        ],
        "diff_text": "### g1:p_0001\n- Due in 45 days.\n+ Due in 30 days.",
    }
    clean = _as_json_dict(payload)
    assert clean == payload


def test_payload_rejects_non_json_objects() -> None:
    with pytest.raises(TypeError, match="JSON-serializable"):
        _as_json_dict({"doc": object()})


async def test_wait_keeps_payload_after_allow_for_apply() -> None:
    broker = ApprovalBroker()
    payload = {
        "source_file_id": "file-1",
        "generation": 2,
        "hashes": {"g2:p_0001": "deadbeef"},
        "operations": [{"op": "delete", "block_id": "g2:p_0001", "hash": "deadbeef"}],
        "diff_text": "### g2:p_0001\n- gone\n+ ",
    }

    async def allow_soon() -> None:
        await asyncio.sleep(0.05)
        assert broker.get_payload("c1", "call1") == payload
        assert broker.resolve("c1", "call1", True)

    task = asyncio.create_task(allow_soon())
    allowed = await broker.wait("c1", "call1", timeout=2.0, payload=payload)
    await task
    assert allowed is True
    # Apply path takes the payload; wait must not drop it on allow.
    assert broker.take_payload("c1", "call1") == payload
    assert broker.get_payload("c1", "call1") is None


async def test_wait_clears_payload_on_deny() -> None:
    broker = ApprovalBroker()
    payload = {
        "source_file_id": "file-1",
        "generation": 1,
        "hashes": {},
        "operations": [],
        "diff_text": "",
    }

    async def deny_soon() -> None:
        await asyncio.sleep(0.05)
        broker.resolve("c1", "call2", False)

    task = asyncio.create_task(deny_soon())
    allowed = await broker.wait("c1", "call2", timeout=2.0, payload=payload)
    await task
    assert allowed is False
    assert broker.get_payload("c1", "call2") is None
