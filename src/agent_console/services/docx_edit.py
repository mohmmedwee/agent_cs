"""Validate `edit_docx` operations and build plaintext diffs (dry-run).

No XML writes here — the executor (slice 4) applies ops after approval.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from agent_console.services.docx_blocks import Block, Manifest

__all__ = [
    "BlockDiff",
    "EditOp",
    "ValidationError",
    "ValidationResult",
    "validate_ops",
]

_BLOCK_ID_RE = re.compile(r"^g(\d+):p_(\d{4})$")


class ValidationError(ValueError):
    """Raised when an op cannot be applied to the tip manifest."""


@dataclass(frozen=True)
class EditOp:
    op: str  # replace | rewrite | insert | delete
    block_id: str | None = None
    old: str | None = None
    new: str | None = None
    content: str | None = None
    hash: str | None = None
    relative_to: str | None = None
    position: str | None = None  # before | after
    new_id: str | None = None  # optional temp id for insert


@dataclass(frozen=True)
class BlockDiff:
    block_id: str
    before: str
    after: str


@dataclass
class ValidationResult:
    ok: bool = True
    diffs: list[BlockDiff] = field(default_factory=list)

    def plaintext(self) -> str:
        lines: list[str] = []
        for d in self.diffs:
            lines.append(f"### {d.block_id}")
            lines.append(f"- {d.before}")
            lines.append(f"+ {d.after}")
        return "\n".join(lines)


def _parse_generation(block_id: str) -> int | None:
    match = _BLOCK_ID_RE.match(block_id)
    return int(match.group(1)) if match else None


def _require_block(manifest: Manifest, block_id: str) -> Block:
    gen = _parse_generation(block_id)
    if gen is None or gen != manifest.generation:
        raise ValidationError(
            f"block id {block_id!r} is not from generation g{manifest.generation}; "
            "re-read the document and use current ids"
        )
    for block in manifest.blocks:
        if block.id == block_id:
            return block
    raise ValidationError(f"unknown block id {block_id!r}; re-read the document")


def _replace_once(text: str, old: str, new: str) -> str:
    """Exact Unicode; Latin letters match case-insensitively for the find."""
    if not old:
        raise ValidationError("replace old text must be non-empty")
    # Prefer exact match count first.
    exact_count = text.count(old)
    if exact_count == 1:
        return text.replace(old, new, 1)
    if exact_count > 1:
        raise ValidationError(
            f"replace old text has {exact_count} matches; refine old or use count later"
        )
    # Latin case-insensitive fallback when exact miss.
    pattern = re.compile(re.escape(old), re.IGNORECASE)
    matches = list(pattern.finditer(text))
    if len(matches) == 0:
        raise ValidationError("replace old text has 0 matches in block")
    if len(matches) > 1:
        raise ValidationError(
            f"replace old text has {len(matches)} matches; refine old or use count later"
        )
    m = matches[0]
    return text[: m.start()] + new + text[m.end() :]


def validate_ops(manifest: Manifest, ops: list[EditOp]) -> ValidationResult:
    """Validate ops against the tip manifest and return plaintext diffs.

    Does not mutate XML or the manifest.
    """
    if not ops:
        raise ValidationError("no operations provided")

    diffs: list[BlockDiff] = []
    # Working text map so sequential ops in one dry-run see prior replaces.
    texts: dict[str, str] = {b.id: b.text for b in manifest.blocks}
    hashes: dict[str, str] = {b.id: b.content_hash for b in manifest.blocks}
    insert_seq = 0

    for op in ops:
        kind = op.op
        if kind == "replace":
            if not op.block_id or op.old is None or op.new is None:
                raise ValidationError("replace requires block_id, old, and new")
            block = _require_block(manifest, op.block_id)
            before = texts[block.id]
            after = _replace_once(before, op.old, op.new)
            texts[block.id] = after
            diffs.append(BlockDiff(block_id=block.id, before=before, after=after))

        elif kind == "rewrite":
            if not op.block_id or op.content is None or not op.hash:
                raise ValidationError("rewrite requires block_id, content, and hash")
            block = _require_block(manifest, op.block_id)
            if op.hash != hashes[block.id]:
                raise ValidationError(
                    f"stale hash for {block.id}: expected {hashes[block.id]}, "
                    f"got {op.hash}; re-read the document"
                )
            before = texts[block.id]
            after = op.content
            texts[block.id] = after
            diffs.append(BlockDiff(block_id=block.id, before=before, after=after))

        elif kind == "delete":
            if not op.block_id or not op.hash:
                raise ValidationError("delete requires block_id and hash")
            block = _require_block(manifest, op.block_id)
            if op.hash != hashes[block.id]:
                raise ValidationError(
                    f"stale hash for {block.id}: expected {hashes[block.id]}, "
                    f"got {op.hash}; re-read the document"
                )
            before = texts[block.id]
            texts[block.id] = ""
            diffs.append(BlockDiff(block_id=block.id, before=before, after=""))

        elif kind == "insert":
            if not op.relative_to or op.content is None:
                raise ValidationError("insert requires relative_to and content")
            position = op.position or "after"
            if position not in ("before", "after"):
                raise ValidationError("insert position must be 'before' or 'after'")
            _require_block(manifest, op.relative_to)
            insert_seq += 1
            temp_id = op.new_id or f"new_{insert_seq}"
            diffs.append(
                BlockDiff(block_id=temp_id, before="", after=op.content)
            )

        else:
            raise ValidationError(f"unknown op {kind!r}")

    return ValidationResult(ok=True, diffs=diffs)
