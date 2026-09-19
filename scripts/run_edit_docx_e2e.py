"""Live / local runner for edit_docx e2e cases.

Usage:
  EDIT_DOCX_E2E=1 uv run python scripts/run_edit_docx_e2e.py
  EDIT_DOCX_E2E=1 EDIT_DOCX_E2E_ROUNDS=5 uv run python scripts/run_edit_docx_e2e.py

Env:
  EDIT_DOCX_E2E_BASE   default http://127.0.0.1:8000
  EDIT_DOCX_E2E_EMAIL / EDIT_DOCX_E2E_PASSWORD  login credentials
  EDIT_DOCX_E2E_MODEL  default from /api/health
  EDIT_DOCX_E2E_CASES  comma-separated case ids (optional filter)
  EDIT_DOCX_E2E_ROUNDS number of full-suite repeats (default 1); writes stability.json
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from collections import defaultdict
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from tests.edit_docx_e2e_corpus import CASES  # noqa: E402
from tests.edit_docx_e2e_score import save_transcript, score_case  # noqa: E402

TRANSCRIPT_DIR = ROOT / "tests" / "fixtures" / "edit_docx_e2e" / "transcripts"
STABILITY_PATH = ROOT / "tests" / "fixtures" / "edit_docx_e2e" / "stability.json"


async def _login(client: httpx.AsyncClient) -> None:
    email = os.environ.get("EDIT_DOCX_E2E_EMAIL", "ehab@example.com")
    password = os.environ.get("EDIT_DOCX_E2E_PASSWORD", "supersecret1")
    resp = await client.post("/api/auth/login", json={"email": email, "password": password})
    if resp.status_code >= 400:
        # Try register then login for disposable accounts.
        await client.post(
            "/api/auth/register",
            json={
                "email": email,
                "password": password,
                "display_name": "e2e",
            },
        )
        resp = await client.post(
            "/api/auth/login", json={"email": email, "password": password}
        )
    resp.raise_for_status()


async def _stream_chat(
    client: httpx.AsyncClient,
    conversation_id: str,
    message: str,
    model: str,
) -> list[dict]:
    events: list[dict] = []
    body = {
        "conversation_id": conversation_id,
        "message": message,
        "model": model,
        "effort": "medium",
        "auto_approve_tools": [
            "edit_docx",
            "write_file",
            "convert_upload_to_docx",
            "run_python",
        ],
    }
    async with client.stream("POST", "/api/chat", json=body) as resp:
        resp.raise_for_status()
        buf = ""
        async for chunk in resp.aiter_text():
            buf += chunk
            while "\n\n" in buf:
                frame, buf = buf.split("\n\n", 1)
                for line in frame.splitlines():
                    if not line.startswith("data:"):
                        continue
                    raw = line[5:].strip()
                    if not raw or raw == "[DONE]":
                        continue
                    try:
                        events.append(json.loads(raw))
                    except json.JSONDecodeError:
                        continue
    return events


async def _tip_text(client: httpx.AsyncClient, name: str, events: list[dict]) -> str:
    """Prefer the file id from the last successful edit_docx result; else newest upload."""
    import re

    file_id = None
    for ev in reversed(events):
        if (ev.get("type") or "") != "tool_result" or (ev.get("name") or "") != "edit_docx":
            continue
        result = str(ev.get("result") or "")
        m = re.search(r"/api/files/([0-9a-f-]+)/download", result)
        if m and not result.startswith("Error:"):
            file_id = m.group(1)
            break
    if not file_id:
        listing = await client.get("/api/files")
        listing.raise_for_status()
        files = listing.json().get("files") or []
        matches = [f for f in files if f.get("name") == name]
        if not matches:
            return ""
        match = max(matches, key=lambda f: str(f.get("uploaded_at") or ""))
        file_id = match["id"]
    # Download raw bytes and extract plain paragraph text (preview is markdown-ish).
    dl = await client.get(f"/api/files/{file_id}/download")
    if dl.status_code >= 400:
        preview = await client.get(f"/api/files/{file_id}/preview")
        if preview.status_code >= 400:
            return ""
        return str(preview.json().get("text") or "")
    from agent_console.services.docx_blocks import block_texts

    return "\n".join(block_texts(dl.content))


async def run_case(client: httpx.AsyncClient, case, model: str) -> dict:
    from uuid import uuid4

    base_name, data = case.builder()
    # Unique name per run — reusing the same tip name across rounds leaves
    # many same-named uploads and the model often skips edit_docx.
    stem = Path(base_name).stem
    name = f"{stem}-{uuid4().hex[:6]}.docx"
    prompt = case.prompt.replace(base_name, name)
    upload = await client.post(
        "/api/files",
        files={
            "files": (
                name,
                data,
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
        },
    )
    upload.raise_for_status()

    created = await client.post(
        "/api/conversations", json={"title": f"e2e-{case.id}"}
    )
    created.raise_for_status()
    conv_id = created.json()["id"]

    events = await _stream_chat(client, conv_id, prompt, model)
    tip = await _tip_text(client, name, events)
    score = score_case(case, events, tip)
    path = save_transcript(
        TRANSCRIPT_DIR,
        case.id,
        events,
        score,
        meta={
            "file": name,
            "conversation_id": conv_id,
            "model": model,
            "tip_excerpt": tip[:500],
        },
    )
    return {"case": case.id, "score": score.to_dict(), "transcript": str(path)}


async def main() -> int:
    if os.environ.get("EDIT_DOCX_E2E") != "1":
        print("Set EDIT_DOCX_E2E=1 to run live agent e2e.", file=sys.stderr)
        return 2
    base = os.environ.get("EDIT_DOCX_E2E_BASE", "http://127.0.0.1:8000")
    filter_ids = {
        x.strip()
        for x in os.environ.get("EDIT_DOCX_E2E_CASES", "").split(",")
        if x.strip()
    }
    rounds = max(1, int(os.environ.get("EDIT_DOCX_E2E_ROUNDS", "1")))
    cases = [c for c in CASES if not filter_ids or c.id in filter_ids]
    tallies: dict[str, list[bool]] = defaultdict(list)
    model = os.environ.get("EDIT_DOCX_E2E_MODEL") or "qwen/qwen3.8-27b"

    async with httpx.AsyncClient(base_url=base, timeout=600.0) as client:
        health = await client.get("/api/health")
        health.raise_for_status()
        model = os.environ.get("EDIT_DOCX_E2E_MODEL") or health.json().get(
            "model", model
        )
        await _login(client)
        last_results: list[dict] = []
        for round_i in range(1, rounds + 1):
            print(f"\n######## round {round_i}/{rounds} ########", flush=True)
            results: list[dict] = []
            for case in cases:
                print(f"\n=== {case.id} (round {round_i}) ===", flush=True)
                try:
                    result = await run_case(client, case, model)
                except Exception as exc:  # noqa: BLE001
                    print(f"FAIL {case.id}: {exc}", flush=True)
                    result = {
                        "case": case.id,
                        "score": {"passed": False, "notes": [str(exc)]},
                    }
                passed = bool(result.get("score", {}).get("passed"))
                tallies[case.id].append(passed)
                print(
                    f"{'PASS' if passed else 'FAIL'} {case.id} "
                    f"notes={result.get('score', {}).get('notes')}",
                    flush=True,
                )
                results.append(result)
            last_results = results

    TRANSCRIPT_DIR.mkdir(parents=True, exist_ok=True)
    summary = TRANSCRIPT_DIR / "summary.json"
    summary.write_text(json.dumps(last_results, indent=2), encoding="utf-8")

    stability = {
        "rounds": rounds,
        "model": model,
        "cases": {
            case_id: {
                "passes": sum(1 for ok in outcomes if ok),
                "runs": len(outcomes),
                "pass_rate": (sum(1 for ok in outcomes if ok) / len(outcomes))
                if outcomes
                else 0.0,
                "outcomes": ["pass" if ok else "fail" for ok in outcomes],
            }
            for case_id, outcomes in sorted(tallies.items())
        },
    }
    STABILITY_PATH.parent.mkdir(parents=True, exist_ok=True)
    STABILITY_PATH.write_text(
        json.dumps(stability, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print("\nPass rates:", flush=True)
    for case_id, info in stability["cases"].items():
        print(
            f"  {case_id}: {info['passes']}/{info['runs']} "
            f"({info['pass_rate']:.0%})",
            flush=True,
        )
    print(f"stability → {STABILITY_PATH}", flush=True)

    any_fail = any(not ok for outcomes in tallies.values() for ok in outcomes)
    return 1 if any_fail else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
