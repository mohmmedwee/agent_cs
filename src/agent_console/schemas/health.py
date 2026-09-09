"""Response schema for the health endpoint."""

from pydantic import BaseModel

__all__ = ["HealthResponse"]


class HealthResponse(BaseModel):
    upstream: str
    ok: bool
    model: str | None = None
    error: str | None = None
