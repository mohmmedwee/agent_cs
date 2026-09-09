"""Persist and remove durable facts about the signed-in user."""

from agent_console.repositories.memory import MemoryLimitError
from agent_console.services.tools.context import ToolContext
from agent_console.services.tools.registry import ToolRegistry

__all__ = ["register"]


def register(registry: ToolRegistry, context: ToolContext) -> None:
    memories = context.memories
    user_id = context.user_id

    @registry.tool(
        name="remember",
        description=(
            "Store a durable fact or preference about this user for future chats "
            "(language, role, project names, likes/dislikes). Use when they say "
            "to remember something, or when a stable preference is clear. Keep "
            "each note to one short sentence."
        ),
        parameters={
            "type": "object",
            "properties": {
                "content": {
                    "type": "string",
                    "description": "One short factual note to keep about the user.",
                }
            },
            "required": ["content"],
        },
    )
    async def remember(content: str) -> str:
        try:
            row = await memories.add(user_id, content, source="agent")
        except MemoryLimitError as exc:
            return f"Error: {exc}"
        return f"Remembered: {row.content}"

    @registry.tool(
        name="forget",
        description=(
            "Remove stored user memories that match a short query (substring). "
            "Use when the user says to forget something, or a note is wrong."
        ),
        parameters={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Text to match against memory contents.",
                }
            },
            "required": ["query"],
        },
    )
    async def forget(query: str) -> str:
        try:
            removed = await memories.delete_matching(user_id, query)
        except MemoryLimitError as exc:
            return f"Error: {exc}"
        if not removed:
            return f"No memories matched {query!r}."
        return "Forgot:\n" + "\n".join(f"- {item}" for item in removed)

    @registry.tool(
        name="list_memories",
        description=(
            "List durable notes already stored about this user. Use before "
            "remembering something that might already be stored."
        ),
        parameters={"type": "object", "properties": {}},
    )
    async def list_memories() -> str:
        rows = await memories.list_for(user_id)
        if not rows:
            return "No memories stored yet."
        return "\n".join(f"- {row.content}" for row in rows)
