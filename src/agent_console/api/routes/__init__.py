"""HTTP route modules, one per resource."""

from agent_console.api.routes import chat, files, health, skills

__all__ = ["chat", "files", "health", "skills"]
