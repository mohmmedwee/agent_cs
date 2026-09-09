"""Replay exactly what AgentService sends, to see where the reply is lost."""

import asyncio

import httpx

from agent_console.clients.upstream import UpstreamClient
from agent_console.config import get_settings
from agent_console.models.chat import ToolSchema


async def main() -> None:
    settings = get_settings()
    async with httpx.AsyncClient() as http:
        client = UpstreamClient(http=http, settings=settings)
        model = await client.resolve_model()
        print("model:", model)

        tools = [
            ToolSchema.model_validate(
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
            )
        ]

        for effort in (None, "minimal"):
            print(f"\n--- effort={effort} ---")
            text, reasoning, message = [], 0, None
            async for chunk in client.stream_completion(
                model=model,
                messages=[{"role": "user", "content": "What is 17 * 23?"}],
                tools=tools,
                known_tool_names={"calculate"},
                effort=effort,
            ):
                if chunk.text:
                    text.append(chunk.text)
                elif chunk.reasoning:
                    reasoning += len(chunk.reasoning)
                else:
                    message = chunk.message
            print("text:", ("".join(text)[:200] or "(none)"))
            print("reasoning chars:", reasoning)
            print("message:", message)


asyncio.run(main())
