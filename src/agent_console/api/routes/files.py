"""Upload endpoints. Uploaded files are reachable by the agent through tools."""

from typing import Annotated

from fastapi import APIRouter, File, HTTPException, UploadFile, status
from fastapi.responses import Response

from agent_console.api.dependencies import FileRepositoryDep
from agent_console.repositories.files import FileTooLargeError, UnknownFileError
from agent_console.schemas.files import FileListResponse, FileUploadResponse

__all__ = ["router"]

router = APIRouter(prefix="/api/files", tags=["files"])


@router.post("", status_code=status.HTTP_201_CREATED)
async def upload_files(
    repository: FileRepositoryDep,
    files: Annotated[list[UploadFile], File()],
) -> FileUploadResponse:
    stored = []
    for upload in files:
        try:
            record = repository.save(
                name=upload.filename or "unnamed",
                data=await upload.read(),
                content_type=upload.content_type,
            )
        except FileTooLargeError as exc:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail=str(exc)
            ) from exc
        stored.append(record)
    return FileUploadResponse(files=stored)


@router.get("")
async def list_files(repository: FileRepositoryDep) -> FileListResponse:
    return FileListResponse(files=repository.list())


@router.get("/{file_id}/download")
async def download_file(file_id: str, repository: FileRepositoryDep) -> Response:
    """Serves both uploads and files the agent wrote via the write_file tool."""
    try:
        record = repository.get(file_id)
        data = repository.raw_bytes(file_id)
    except UnknownFileError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    return Response(
        content=data,
        media_type=record.content_type or "application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{record.name}"'},
    )
