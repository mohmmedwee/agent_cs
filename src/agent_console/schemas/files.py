"""Request and response shapes for uploaded files."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

__all__ = [
    "FileListResponse",
    "FilePreviewResponse",
    "FileResponse",
    "FileUploadResponse",
]


class FileResponse(BaseModel):
    id: UUID
    name: str
    size: int
    content_type: str | None = None
    is_text: bool
    is_image: bool = False
    uploaded_at: datetime

    model_config = {"from_attributes": True}


class FilePreviewResponse(BaseModel):
    id: UUID
    name: str
    text: str
    truncated: bool = False


class FileListResponse(BaseModel):
    files: list[FileResponse]


class FileUploadResponse(BaseModel):
    files: list[FileResponse]
