"""Dump the raw SSE the endpoint returns, with and without tools."""

import asyncio
import json

import httpx

URL = "http://172.25.44.38:1234/v1/chat/completions"
MODEL = "qwen/qwen3.8-27b"

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "calculate",
            "description": "Evaluate an arithmetic expression.",
            "parameters": {
                "type": "object",
                "properties": {"expression": {"type": "string"}},
                "required": ["expression"],
            },
        },
    }
]


async def probe(label: str, body: dict) -> None:
    print(f"\n=== {label} ===")
    print("request keys:", sorted(body))
    async with httpx.AsyncClient() as http:
        async with http.stream("POST", URL, json=body, timeout=300) as response:
            print("status:", response.status_code)
            if response.status_code >= 400:
                print("body:", (await response.aread()).decode()[:500])
                return
            count = 0
            async for line in response.aiter_lines():
                if not line.strip():
                    continue
                count += 1
                if count <= 6:
                    print("  line:", line[:220])
            print("total lines:", count)


async def main() -> None:
    base = {
        "model": MODEL,
        "messages": [{"role": "user", "content": "What is 17 * 23?"}],
        "stream": True,
        "temperature": 0.7,
    }
    await probe("no tools", dict(base))
    await probe("with tools", {**base, "tools": TOOLS, "tool_choice": "auto"})


asyncio.run(main())
