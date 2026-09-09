"""Real clock access — the classic thing a model cannot know on its own."""

from datetime import datetime, timezone

from agent_console.services.tools.context import ToolContext
from agent_console.services.tools.registry import ToolRegistry

__all__ = ["register"]


def register(registry: ToolRegistry, context: ToolContext) -> None:
    @registry.tool(
        name="get_current_time",
        description="Current date and time. Use for anything about today, now, or elapsed time.",
        parameters={
            "type": "object",
            "properties": {
                "timezone_name": {
                    "type": "string",
                    "description": "IANA name, e.g. Asia/Amman or Asia/Dubai. Defaults to UTC.",
                }
            },
        },
    )
    def get_current_time(timezone_name: str = "UTC") -> str:
        try:
            from zoneinfo import ZoneInfo

            tz = ZoneInfo(timezone_name)
        except Exception:
            tz, timezone_name = timezone.utc, "UTC"
        return f"{datetime.now(tz).strftime('%Y-%m-%d %H:%M:%S')} ({timezone_name})"
