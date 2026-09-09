"""End-to-end check that a chat turn streams and persists."""

import asyncio
import json
import sys

import httpx

BASE = "http://127.0.0.1:8000"
CREDENTIALS = {"email": "ehab@example.com", "password": "supersecret1"}
PROMPT = "What is 17 * 23? Use your calculator tool, then state the number."


MODEL = "qwen/qwen3.8-27b"


async def run_turn(client: httpx.AsyncClient, conversation_id: str, prompt: str) -> None:
        seen: dict[str, int] = {}
        answer: list[str] = []

        async with client.stream(
            "POST",
            "/api/chat",
            json={
                "conversation_id": conversation_id,
                "message": prompt,
                "effort": "minimal",
                "model": MODEL,
            },
        ) as response:
            print("chat", response.status_code)
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
                    print(f"  tool_call  {event['name']} {event['arguments'][:80]}")
                elif kind == "tool_result":
                    print(f"  result     {event['result'][:80]}")
                elif kind == "error":
                    print(f"  ERROR      {event['message'][:200]}")

        print("events:", seen)
        print("answer:", "".join(answer).strip()[:400] or "(empty)")


async def main() -> None:
    async with httpx.AsyncClient(base_url=BASE, timeout=900) as client:
        login = await client.post("/api/auth/login", json=CREDENTIALS)
        print("login", login.status_code)
        login.raise_for_status()

        created = await client.post("/api/conversations", json={"title": "smoke"})
        conversation_id = created.json()["id"]
        print("conversation", conversation_id)

        print("\n--- turn 1: tool use ---")
        await run_turn(client, conversation_id, PROMPT)

        print("\n--- turn 2: vision ---")
        from probe_vision import make_png  # reuses the generated blue square

        upload = await client.post(
            "/api/files", files={"files": ("square.png", make_png(), "image/png")}
        )
        record = upload.json()["files"][0]
        print(f"uploaded {record['name']} is_image={record['is_image']}")
        await run_turn(
            client,
            conversation_id,
            "Look at the uploaded image square.png and tell me what colour the "
            "square is.",
        )

        print("\n--- persistence ---")
        stored = await client.get(f"/api/conversations/{conversation_id}")
        payload = stored.json()
        print("title:", payload["title"])
        for message in payload["messages"]:
            kinds = [b["kind"] for b in (message["blocks"] or [])]
            print(
                f"  {message['role']:9s} {len(message['content']):5d} chars  blocks={kinds}"
            )


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
