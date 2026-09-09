"""Domain types for uploaded files."""

from datetime import datetime

from pydantic import BaseModel

__all__ = ["StoredFile"]


class StoredFile(BaseModel):
    id: str
    name: str
    size: int
    content_type: str | None = None
    uploaded_at: datetime
    is_text: bool
