"""Reproduce the run that dead-ended: a .docx deliverable at minimal effort.

Two things went wrong there. The skill load ate half the two-step budget, so the
turn ended on 'Stopped after 2 tool steps' with no answer, and the file it had
written was Markdown wearing a .docx extension.
"""

import asyncio
import json
import subprocess
import sys
import tempfile
from pathlib import Path

import httpx

BASE = "http://127.0.0.1:8000"
CREDENTIALS = {"email": "ehab@example.com", "password": "supersecret1"}
PROMPT = (
    "I need a document about animals for kids, covering mammals, birds, "
    "reptiles, fish and insects. Around 600 words. Give it to me as a docx."
)


async def main() -> None:
    async with httpx.AsyncClient(base_url=BASE, timeout=1200) as client:
        login = await client.post("/api/auth/login", json=CREDENTIALS)
        login.raise_for_status()

        created = await client.post("/api/conversations", json={"title": "docx smoke"})
        conversation_id = created.json()["id"]

        seen: dict[str, int] = {}
        answer: list[str] = []
        download: str | None = None

        async with client.stream(
            "POST",
            "/api/chat",
            json={
                "conversation_id": conversation_id,
                "message": PROMPT,
                "effort": "minimal",
                "model": "qwen/qwen3.8-27b",
            },
        ) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if not line.startswith("data:"):
                    continue
                event = json.loads(line[5:])
                kind = event["type"]
                seen[kind] = seen.get(kind, 0) + 1
                if kind == "text_delta":
                    answer.append(event["text"])
                elif kind == "tool_call":
                    print(f"  tool_call  {event['name']} {event['arguments'][:70]}")
                elif kind == "tool_result":
                    print(f"  result     {event['result'][:110]}")
                    if "/download" in event["result"]:
                        download = event["result"].split("Download: ")[-1].strip()
                elif kind == "error":
                    print(f"  ERROR      {event['message'][:200]}")

        print("events:", seen)
        print("answer:", "".join(answer).strip()[:500] or "(EMPTY)")

        if not download:
            print("\nno file was written")
            return

        print(f"\n--- downloading {download} ---")
        got = await client.get(download)
        got.raise_for_status()
        print("content-type:", got.headers.get("content-type"))
        print("bytes:", len(got.content))

        path = Path(tempfile.gettempdir()) / "agent-animals.docx"
        path.write_bytes(got.content)
        # Apple's own OOXML parser: an independent check that Word would open it.
        info = subprocess.run(
            ["textutil", "-info", str(path)], capture_output=True, text=True
        )
        print(info.stdout.strip() or info.stderr.strip())


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
