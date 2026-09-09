"""Response schemas for the file endpoints."""

from pydantic import BaseModel

from agent_console.models.files import StoredFile

__all__ = ["FileListResponse", "FileUploadResponse"]


class FileUploadResponse(BaseModel):
    files: list[StoredFile]


class FileListResponse(BaseModel):
    files: list[StoredFile]
