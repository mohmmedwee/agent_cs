"""Recognising images by their content rather than by their file name.

Extensions lie — a screenshot saved as `.txt` is still a PNG, and a `.jpg`
that is really HTML would be sent to the vision model as garbage. Magic bytes
do not lie, so detection reads the header.
"""

import base64

__all__ = ["MIME_BY_SIGNATURE", "image_media_type", "to_data_url"]

# (offset, signature, media type)
_SIGNATURES: list[tuple[int, bytes, str]] = [
    (0, b"\x89PNG\r\n\x1a\n", "image/png"),
    (0, b"\xff\xd8\xff", "image/jpeg"),
    (0, b"GIF87a", "image/gif"),
    (0, b"GIF89a", "image/gif"),
    (0, b"BM", "image/bmp"),
]

MIME_BY_SIGNATURE = {media for _, _, media in _SIGNATURES} | {"image/webp"}


def image_media_type(data: bytes) -> str | None:
    """The image's media type, or None if these bytes are not an image."""
    for offset, signature, media_type in _SIGNATURES:
        if data[offset : offset + len(signature)] == signature:
            return media_type

    # WebP and other RIFF containers carry their format in a second tag.
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


def to_data_url(data: bytes, media_type: str) -> str:
    return f"data:{media_type};base64,{base64.b64encode(data).decode('ascii')}"
