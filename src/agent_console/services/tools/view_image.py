"""Gives the agent eyes.

The reasoning model is text-only, so instead of feeding it pixels this tool
sends the image to a multimodal model and hands back the answer as text. The
agent asks a specific question and reasons over the reply, which means vision
works no matter which chat model the user has selected.
"""

from agent_console.clients.upstream import UpstreamError
from agent_console.repositories.files import UnknownFileError
from agent_console.repositories.images import image_media_type, to_data_url
from agent_console.services.tools.context import ToolContext
from agent_console.services.tools.registry import ToolRegistry

__all__ = ["register"]


def register(registry: ToolRegistry, context: ToolContext) -> None:
    files = context.files
    user_id = context.user_id
    upstream = context.upstream
    settings = context.settings

    @registry.tool(
        name="view_image",
        description=(
            "Look at an uploaded image and answer a question about it. Use for "
            "screenshots, photos, diagrams, charts, or scanned documents. Ask "
            "something specific — 'what error does this screenshot show?', "
            "'transcribe the text', 'describe this chart' — because you get back "
            "only the answer, not the image itself. Ask again for more detail."
        ),
        parameters={
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "The image's file name or id.",
                },
                "question": {
                    "type": "string",
                    "description": "What you want to know about the image.",
                },
            },
            "required": ["name", "question"],
        },
    )
    async def view_image(name: str, question: str) -> str:
        try:
            data = await files.raw_bytes(user_id, name)
        except UnknownFileError as exc:
            available = ", ".join(row.name for row in await files.list_for(user_id))
            return f"Error: {exc}. Uploaded files: {available or 'none'}"

        media_type = image_media_type(data)
        if media_type is None:
            return (
                f"Error: {name} is not an image this server recognises "
                "(PNG, JPEG, GIF, BMP, and WebP are supported)."
            )
        if len(data) > settings.max_image_bytes:
            return (
                f"Error: {name} is {len(data) // 1024} KB, over the "
                f"{settings.max_image_bytes // 1024} KB limit for images."
            )

        try:
            return await upstream.describe_image(
                data_url=to_data_url(data, media_type),
                question=question,
                model=settings.vision_model,
                timeout=settings.vision_timeout,
            )
        except UpstreamError as exc:
            return f"Error: {exc}"
