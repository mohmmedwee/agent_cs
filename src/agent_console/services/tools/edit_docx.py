"""edit_docx — validate, approve with a server-built diff card, then apply."""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID

from agent_console.repositories.files import (
    FileRepository,
    FileTooLargeError,
    UnknownFileError,
)
from agent_console.services.docx_approval import build_approval_card
from agent_console.services.docx_blocks import assign_fresh_manifest
from agent_console.services.docx_edit import (
    EditOp,
    ValidationError,
    apply_ops,
    ops_from_payload,
    validate_ops,
)
from agent_console.services.tools.context import ToolContext
from agent_console.services.tools.registry import ToolRegistry

__all__ = [
    "apply_edit_docx_payload",
    "prepare_edit_docx_approval",
    "register",
]

DOCX_MEDIA_TYPE = (
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
)


def _parse_ops(raw: Any) -> list[EditOp]:
    if not isinstance(raw, list) or not raw:
        raise ValidationError("operations must be a non-empty list")
    ops: list[EditOp] = []
    for item in raw:
        if not isinstance(item, dict):
            raise ValidationError("each operation must be an object")
        ops.append(
            EditOp(
                op=str(item.get("op") or ""),
                block_id=item.get("block_id"),
                old=item.get("old"),
                new=item.get("new"),
                content=item.get("content"),
                hash=item.get("hash"),
                relative_to=item.get("relative_to"),
                position=item.get("position"),
                new_id=item.get("new_id"),
            )
        )
    return ops


async def prepare_edit_docx_approval(
    files: FileRepository,
    user_id: UUID,
    raw_arguments: str,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None, str | None]:
    """Dry-run validate and build (payload, approval_card, error)."""
    try:
        args = json.loads(raw_arguments) if raw_arguments else {}
    except json.JSONDecodeError:
        return None, None, "Error: invalid JSON arguments for edit_docx"
    if not isinstance(args, dict):
        return None, None, "Error: edit_docx arguments must be an object"

    name = str(args.get("name") or "").strip()
    if not name:
        return None, None, "Error: name is required"

    try:
        tip = await files.latest_in_chain(user_id, name)
        data = await files.raw_bytes(user_id, str(tip.id))
    except UnknownFileError as exc:
        return None, None, f"Error: {exc}"

    if not tip.name.lower().endswith(".docx"):
        return None, None, f"Error: {tip.name} is not a .docx file"

    try:
        ops = _parse_ops(args.get("operations"))
        generation = int(args.get("generation") or 1)
        manifest = assign_fresh_manifest(data, generation=generation)
        result = validate_ops(manifest, ops)
    except (ValidationError, ValueError, TypeError) as exc:
        return None, None, f"Error: {exc}"

    hashes = {b.id: b.content_hash for b in manifest.blocks}
    payload = {
        "source_file_id": str(tip.id),
        "file_name": tip.name,
        "from_version": tip.version or 1,
        "generation": manifest.generation,
        "hashes": hashes,
        "operations": [
            {
                "op": op.op,
                "block_id": op.block_id,
                "old": op.old,
                "new": op.new,
                "content": op.content,
                "hash": op.hash,
                "relative_to": op.relative_to,
                "position": op.position,
                "new_id": op.new_id,
            }
            for op in ops
        ],
        "diff_text": result.plaintext(),
    }
    card = build_approval_card(
        file_name=tip.name,
        from_version=tip.version or 1,
        diffs=result.diffs,
        ops=ops,
    )
    return payload, card, None


async def apply_edit_docx_payload(
    files: FileRepository, user_id: UUID, payload: dict[str, Any]
) -> str:
    """Revalidate tip + apply ops from a consumed approval payload."""
    try:
        tip = await files.latest_in_chain(user_id, str(payload["source_file_id"]))
        data = await files.raw_bytes(user_id, str(tip.id))
    except UnknownFileError as exc:
        return f"Error: {exc}"

    if str(tip.id) != str(payload.get("source_file_id")):
        return (
            "Error: document changed, nothing applied (tip moved). "
            "Re-read and try again."
        )

    try:
        ops = ops_from_payload(payload)
        gen = int(payload.get("generation") or 1)
        manifest = assign_fresh_manifest(data, generation=gen)
        validate_ops(manifest, ops)
        out, new_manifest, diffs = apply_ops(data, manifest, ops)
    except ValidationError as exc:
        return (
            f"Error: document changed, nothing applied ({exc}). "
            "Re-read the tip and propose the edit again."
        )
    except ValueError as exc:
        return f"Error: {exc}"

    try:
        saved = await files.save(
            user_id,
            name=tip.name,
            data=out,
            content_type=DOCX_MEDIA_TYPE,
            parent_id=tip.id,
            derived_from=tip.id,
        )
    except FileTooLargeError as exc:
        return f"Error: {exc}"
    except Exception as exc:  # noqa: BLE001
        return (
            f"Error: document changed, nothing applied ({exc}). "
            "Re-read the tip and try again."
        )

    bits = "; ".join(f"{d.block_id}: {d.before!r} → {d.after!r}" for d in diffs[:5])
    more = f" (+{len(diffs) - 5} more)" if len(diffs) > 5 else ""
    return (
        f"Updated {saved.name} v{tip.version} → v{saved.version} "
        f"({len(diffs)} change(s), generation g{new_manifest.generation}). "
        f"{bits}{more} "
        f"Download: /api/files/{saved.id}/download"
    )


def register(registry: ToolRegistry, context: ToolContext) -> None:
    files = context.files
    user_id = context.user_id

    @registry.tool(
        name="edit_docx",
        description=(
            "Edit an uploaded .docx by block id (from annotated read/search). "
            "Ops: replace, rewrite, insert, delete. Requires approval; the "
            "server shows a plaintext diff before applying."
        ),
        parameters={
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "DOCX file name or id (chain tip is used).",
                },
                "generation": {
                    "type": "integer",
                    "description": "Manifest generation from the annotated read (default 1).",
                },
                "operations": {
                    "type": "array",
                    "description": "List of edit operations.",
                    "items": {"type": "object"},
                },
            },
            "required": ["name", "operations"],
        },
    )
    async def edit_docx(
        name: str,
        operations: list[dict[str, Any]] | None = None,
        generation: int = 1,
    ) -> str:
        # Direct invoke (tests / auto-approve): validate and apply without payload.
        _, _, err = await prepare_edit_docx_approval(
            files,
            user_id,
            json.dumps(
                {"name": name, "operations": operations or [], "generation": generation}
            ),
        )
        if err:
            return err
        tip = await files.latest_in_chain(user_id, name)
        data = await files.raw_bytes(user_id, str(tip.id))
        ops = _parse_ops(operations)
        manifest = assign_fresh_manifest(data, generation=int(generation or 1))
        try:
            out, new_manifest, diffs = apply_ops(data, manifest, ops)
            saved = await files.save(
                user_id,
                name=tip.name,
                data=out,
                content_type=DOCX_MEDIA_TYPE,
                parent_id=tip.id,
                derived_from=tip.id,
            )
        except ValidationError as exc:
            return f"Error: {exc}"
        except Exception as exc:  # noqa: BLE001
            return f"Error: {exc}"
        return (
            f"Updated {saved.name} v{tip.version} → v{saved.version} "
            f"({len(diffs)} change(s), generation g{new_manifest.generation}). "
            f"Download: /api/files/{saved.id}/download"
        )
