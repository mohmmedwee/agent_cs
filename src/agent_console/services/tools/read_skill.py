"""Lets the model load a skill's full instructions when it judges one relevant.

This is the second half of progressive disclosure: the system prompt advertises
each skill in one line, and this tool pays for the body only on demand.
"""

from agent_console.repositories.skills import UnknownSkillError
from agent_console.services.tools.context import ToolContext
from agent_console.services.tools.registry import ToolRegistry

__all__ = ["register"]


def register(registry: ToolRegistry, context: ToolContext) -> None:
    skills = context.skills
    max_chars = context.settings.max_skill_chars

    @registry.tool(
        name="read_skill",
        description=(
            "Load the full instructions for one of your available skills. "
            "Call this as your FIRST action whenever a skill's description matches "
            "the task, then follow the instructions it returns."
        ),
        parameters={
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "The skill name exactly as listed in your available skills.",
                }
            },
            "required": ["name"],
        },
    )
    def read_skill(name: str) -> str:
        try:
            return skills.read(name, max_chars=max_chars)
        except UnknownSkillError as exc:
            return f"Error: {exc}"
