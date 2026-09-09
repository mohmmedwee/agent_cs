"""Dependency wiring for the API layer.

Collaborators are built once during startup and shared, so requests reuse
pooled connections, the resolved-model cache, and the loaded skill index rather
than rebuilding all three on every call.
"""

from typing import Annotated

from fastapi import Depends, Request

from agent_console.clients.upstream import UpstreamClient
from agent_console.config import Settings
from agent_console.repositories.files import FileRepository
from agent_console.repositories.skills import SkillRepository
from agent_console.services.agent import AgentService
from agent_console.services.tools import ToolRegistry

__all__ = [
    "AgentServiceDep",
    "FileRepositoryDep",
    "SettingsDep",
    "SkillRepositoryDep",
    "ToolRegistryDep",
    "UpstreamClientDep",
]


def _settings(request: Request) -> Settings:
    return request.app.state.settings


def _tool_registry(request: Request) -> ToolRegistry:
    return request.app.state.tool_registry


def _upstream_client(request: Request) -> UpstreamClient:
    return request.app.state.upstream_client


def _file_repository(request: Request) -> FileRepository:
    return request.app.state.file_repository


def _skill_repository(request: Request) -> SkillRepository:
    return request.app.state.skill_repository


def _agent_service(request: Request) -> AgentService:
    state = request.app.state
    return AgentService(
        upstream=state.upstream_client,
        tools=state.tool_registry,
        settings=state.settings,
        skills=state.skill_repository,
    )


SettingsDep = Annotated[Settings, Depends(_settings)]
ToolRegistryDep = Annotated[ToolRegistry, Depends(_tool_registry)]
UpstreamClientDep = Annotated[UpstreamClient, Depends(_upstream_client)]
FileRepositoryDep = Annotated[FileRepository, Depends(_file_repository)]
SkillRepositoryDep = Annotated[SkillRepository, Depends(_skill_repository)]
AgentServiceDep = Annotated[AgentService, Depends(_agent_service)]
