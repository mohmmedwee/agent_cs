"""Upload endpoints. Uploaded files are reachable by the agent through tools."""

from typing import Annotated
from urllib.parse import quote
from uuid import UUID

from fastapi import APIRouter, File, HTTPException, UploadFile, status
from fastapi.responses import Response

from agent_console.api.dependencies import CurrentUserDep, FileRepositoryDep
from agent_console.repositories.extraction import (
    docx_media_bytes,
    docx_preview_markdown,
)
from agent_console.repositories.files import (
    FileTooLargeError,
    UnknownFileError,
    UnreadableFileError,
)
from agent_console.schemas.files import (
    FileListResponse,
    FilePreviewResponse,
    FileResponse,
    FileUploadResponse,
)

__all__ = ["router"]

router = APIRouter(prefix="/api/files", tags=["files"])


@router.post("", status_code=status.HTTP_201_CREATED)
async def upload_files(
    user: CurrentUserDep,
    repository: FileRepositoryDep,
    files: Annotated[list[UploadFile], File()],
) -> FileUploadResponse:
    stored = []
    for upload in files:
        try:
            record = await repository.save(
                user.id,
                name=upload.filename or "unnamed",
                data=await upload.read(),
                content_type=upload.content_type,
            )
        except FileTooLargeError as exc:
            raise HTTPException(
                status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, str(exc)
            ) from exc
        stored.append(FileResponse.model_validate(record))
    return FileUploadResponse(files=stored)


@router.get("")
async def list_files(
    user: CurrentUserDep, repository: FileRepositoryDep
) -> FileListResponse:
    rows = await repository.list_for(user.id)
    return FileListResponse(files=[FileResponse.model_validate(row) for row in rows])


@router.delete("/{file_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_file(
    file_id: UUID, user: CurrentUserDep, repository: FileRepositoryDep
) -> None:
    try:
        await repository.delete(user.id, str(file_id))
    except UnknownFileError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc


@router.get("/{file_id}/preview")
async def preview_file(
    file_id: UUID, user: CurrentUserDep, repository: FileRepositoryDep
) -> FilePreviewResponse:
    """Readable text of a stored file, for in-chat document previews.

    Caps the window so a long report does not flood the browser; the download
    still carries the full document. Docx previews include image markers that
    resolve through `/docx-media/`.
    """
    limit = 12_000
    try:
        record = await repository.get(user.id, str(file_id))
        if record.name.lower().endswith(".docx"):
            data = await repository.raw_bytes(user.id, str(file_id))
            full = docx_preview_markdown(data, str(record.id))
            if full is None:
                raise UnreadableFileError(f"{record.name} could not be previewed")
        else:
            full = await repository.text(user.id, str(file_id))
    except UnknownFileError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    except UnreadableFileError as exc:
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, str(exc)) from exc

    return FilePreviewResponse(
        id=record.id,
        name=record.name,
        text=full[:limit],
        truncated=len(full) > limit,
    )


@router.get("/{file_id}/docx-media/{media_name}")
async def preview_docx_media(
    file_id: UUID,
    media_name: str,
    user: CurrentUserDep,
    repository: FileRepositoryDep,
) -> Response:
    """An embedded image from a .docx, for the artifact preview pane."""
    try:
        record = await repository.get(user.id, str(file_id))
        if not record.name.lower().endswith(".docx"):
            raise HTTPException(status.HTTP_404_NOT_FOUND, "not a Word document")
        data = await repository.raw_bytes(user.id, str(file_id))
    except UnknownFileError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc

    extracted = docx_media_bytes(data, media_name)
    if extracted is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "media not found")
    payload, content_type = extracted
    return Response(content=payload, media_type=content_type)


@router.get("/{file_id}/download")
async def download_file(
    file_id: UUID, user: CurrentUserDep, repository: FileRepositoryDep
) -> Response:
    """Serves both uploads and files the agent wrote via the write_file tool."""
    try:
        record = await repository.get(user.id, str(file_id))
        data = await repository.raw_bytes(user.id, str(file_id))
    except UnknownFileError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc

    # RFC 5987 encoding, so Arabic and other non-ASCII names survive the header.
    # Images need inline disposition so chat thumbnails / the artifact pane can
    # render them via <img src>. The Download button still uses the download=
    # attribute to save a copy.
    disposition = (
        "inline"
        if (record.content_type or "").startswith("image/")
        else "attachment"
    )
    return Response(
        content=data,
        media_type=record.content_type or "application/octet-stream",
        headers={
            "Content-Disposition": (
                f"{disposition}; filename*=UTF-8''{quote(record.name)}"
            )
        },
    )
