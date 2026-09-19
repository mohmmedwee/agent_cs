"""Convert / lightly patch an uploaded Markdown file into a .docx on the server.

Large uploads blow up local models when the agent re-emits the whole body through
`write_file`. This tool keeps the body on disk: the model only passes small args
(source, theme, find/replace patches, or one-section rewrites).
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from agent_console.repositories.documents import DOCX_MEDIA_TYPE, build_docx
from agent_console.repositories.files import (
    FileTooLargeError,
    UnknownFileError,
    UnreadableFileError,
)
from agent_console.services.tools.context import ToolContext
from agent_console.services.tools.registry import ToolRegistry

__all__ = ["register"]

_SOURCE_SUFFIXES = {".md", ".markdown", ".txt", ".text", ".csv"}
_HEADING = re.compile(r"^(#{1,6})\s+(.*)$", re.MULTILINE)
# Cap each patch so a "section update" cannot become a full-document rewrite.
_MAX_PATCH_CHARS = 24_000


def _as_object_list(value: Any) -> list[dict[str, Any]]:
    if value is None or value == "":
        return []
    if isinstance(value, dict):
        return [value]
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    return []


def _apply_replacements(
    markdown: str, replacements: list[dict[str, Any]]
) -> tuple[str | None, list[str]]:
    """Apply find/replace patches. Fail closed on 0 or ambiguous matches.

    Returns (new_text, notes) on success, or (None, [error]) on failure.
    Multiple matches require `count` (e.g. 1 = first only) or `replace_all: true`.
    """
    notes: list[str] = []
    text = markdown
    for index, item in enumerate(replacements, start=1):
        find = str(item.get("find") or item.get("old") or "")
        if "replace" in item:
            repl = str(item.get("replace") or "")
        else:
            repl = str(item.get("new") or "")
        if not find:
            notes.append(f"replacement {index}: skipped (empty find)")
            continue
        if len(find) > _MAX_PATCH_CHARS or len(repl) > _MAX_PATCH_CHARS:
            return None, [
                f"Error: replacement {index}: find/replace over "
                f"{_MAX_PATCH_CHARS} chars — split the edit."
            ]
        hits = text.count(find)
        preview = find if len(find) <= 80 else f"{find[:80]}…"
        if hits == 0:
            return None, [
                f"Error: replacement {index}: not found ({preview!r})."
            ]

        limit = item.get("count")
        try:
            limit_n = int(limit) if limit not in (None, "") else 0
        except (TypeError, ValueError):
            limit_n = 0
        replace_all = bool(item.get("replace_all"))

        if limit_n > 0:
            text = text.replace(find, repl, limit_n)
            notes.append(
                f"replacement {index}: replaced {min(hits, limit_n)}×"
            )
        elif replace_all or hits == 1:
            text = text.replace(find, repl)
            notes.append(f"replacement {index}: replaced {hits}×")
        else:
            return None, [
                f"Error: replacement {index}: found {hits} matches for "
                f"{preview!r}; pass count: 1 for the first only, or "
                "replace_all: true to change all."
            ]
    return text, notes


def _heading_titles(markdown: str, limit: int = 24) -> list[str]:
    titles = [f"{m.group(1)} {m.group(2).strip()}" for m in _HEADING.finditer(markdown)]
    return titles[:limit]


def _apply_section_replacements(
    markdown: str, sections: list[dict[str, Any]]
) -> tuple[str | None, list[str]]:
    """Replace the body under a matched heading; keep the rest of the file."""
    notes: list[str] = []
    text = markdown
    for index, item in enumerate(sections, start=1):
        heading = str(item.get("heading") or item.get("section") or "").strip()
        content = str(item.get("content") or item.get("body") or "")
        if not heading:
            notes.append(f"section {index}: skipped (empty heading)")
            continue
        if len(content) > _MAX_PATCH_CHARS:
            return None, [
                f"Error: section {index} content is {len(content)} chars; max "
                f"is {_MAX_PATCH_CHARS}. Split into smaller section updates — "
                "do not paste the whole document."
            ]
        needle = heading.lstrip("#").strip().lower()
        matches = list(_HEADING.finditer(text))
        chosen = None
        for position, match in enumerate(matches):
            title = match.group(2).strip()
            if needle == title.lower() or needle in title.lower():
                chosen = (position, match)
                break
        if chosen is None:
            available = ", ".join(_heading_titles(text)) or "(none)"
            notes.append(
                f"section {index}: heading {heading!r} not found. "
                f"Available: {available}"
            )
            continue
        position, match = chosen
        level = len(match.group(1))
        start = match.start()
        end = len(text)
        for later in matches[position + 1 :]:
            if len(later.group(1)) <= level:
                end = later.start()
                break
        heading_line = match.group(0).rstrip()
        body = content.strip()
        chunk = heading_line + ("\n\n" + body if body else "\n") + "\n\n"
        text = text[:start] + chunk + text[end:].lstrip("\n")
        notes.append(f"section {index}: replaced under {match.group(2).strip()!r}")
    return text, notes


def register(registry: ToolRegistry, context: ToolContext) -> None:
    files = context.files
    user_id = context.user_id

    @registry.tool(
        name="convert_upload_to_docx",
        description=(
            "Build a branded .docx from an uploaded Markdown/text file on the "
            "server. Prefer this over `write_file` for uploads (especially long "
            "reports). Optional content updates: pass `replacements` "
            "(find→replace snippets) and/or `sections` (rewrite one heading's "
            "body only). Never read the whole file into chat and rewrite it. "
            "Returns the download link."
        ),
        parameters={
            "type": "object",
            "properties": {
                "source": {
                    "type": "string",
                    "description": (
                        "Uploaded file name or id (.md / .markdown / .txt)."
                    ),
                },
                "name": {
                    "type": "string",
                    "description": (
                        "Output .docx file name. Defaults to the source stem "
                        "with .docx."
                    ),
                },
                "theme": {
                    "type": "string",
                    "description": (
                        "Document theme: cleverso, classic, modern, warm, or "
                        "editorial. Overrides front matter in the source."
                    ),
                },
                "title": {
                    "type": "string",
                    "description": "Optional document title (Word Title style).",
                },
                "author": {
                    "type": "string",
                    "description": "Optional author metadata.",
                },
                "toc": {
                    "type": "boolean",
                    "description": "Insert a table of contents. Default true.",
                },
                "page_numbers": {
                    "type": "boolean",
                    "description": "Insert page numbers in the footer. Default true.",
                },
                "rtl": {
                    "type": "boolean",
                    "description": "Right-to-left section for Arabic/Hebrew docs.",
                },
                "replacements": {
                    "type": "array",
                    "description": (
                        "Small find/replace edits. Each item: "
                        '{"find":"old","replace":"new"}. Exactly one match '
                        "required unless count (e.g. 1 = first only) or "
                        "replace_all: true is set. Zero matches fails the tool."
                    ),
                    "items": {
                        "type": "object",
                        "properties": {
                            "find": {"type": "string"},
                            "replace": {"type": "string"},
                            "count": {"type": "integer"},
                            "replace_all": {"type": "boolean"},
                        },
                    },
                },
                "sections": {
                    "type": "array",
                    "description": (
                        "Rewrite the body under one Markdown heading without "
                        "touching the rest. Each item: "
                        '{"heading":"TC-02","content":"## new markdown…"}.'
                    ),
                    "items": {
                        "type": "object",
                        "properties": {
                            "heading": {"type": "string"},
                            "content": {"type": "string"},
                        },
                    },
                },
            },
            "required": ["source"],
        },
    )
    async def convert_upload_to_docx(
        source: str,
        name: str = "",
        theme: str = "",
        title: str = "",
        author: str = "",
        toc: bool = True,
        page_numbers: bool = True,
        rtl: bool = False,
        replacements: Any = None,
        sections: Any = None,
    ) -> str:
        try:
            row = await files.get(user_id, source)
        except UnknownFileError as exc:
            available = ", ".join(r.name for r in await files.list_for(user_id))
            return f"Error: {exc}. Uploaded files: {available or 'none'}"

        suffix = Path(row.name).suffix.lower()
        if suffix and suffix not in _SOURCE_SUFFIXES:
            return (
                f"Error: convert_upload_to_docx expects Markdown or plain text "
                f"(.md / .txt); got {row.name!r}. To edit an existing .docx use "
                "`run_python` with python-docx (stage the file via `inputs`), "
                "or for a short new doc use `write_file` with a .docx name."
            )

        try:
            markdown = await files.text(user_id, str(row.id))
        except UnreadableFileError as exc:
            return f"Error: {exc}"

        if not markdown.strip():
            return f"Error: {row.name} is empty — nothing to convert."

        notes: list[str] = []
        replacement_items = _as_object_list(replacements)
        section_items = _as_object_list(sections)

        if replacement_items:
            patched, repl_notes = _apply_replacements(markdown, replacement_items)
            if patched is None:
                return repl_notes[0]
            markdown = patched
            notes.extend(repl_notes)

        if section_items:
            patched, section_notes = _apply_section_replacements(
                markdown, section_items
            )
            if patched is None:
                return section_notes[0]
            markdown = patched
            notes.extend(section_notes)

        out_name = (name or "").strip() or f"{Path(row.name).stem}.docx"
        if not out_name.lower().endswith(".docx"):
            out_name = f"{out_name}.docx"

        # Refuse to rebuild over a tip that was edited (or came from another
        # source). Convert always regenerates from the markdown, so parenting
        # the tip alone still wipes content — that was a live data-loss bug.
        parent_id = None
        try:
            existing = await files.get(user_id, out_name)
        except UnknownFileError:
            existing = None
        if existing is not None:
            tip = await files.latest_in_chain(user_id, str(existing.id))
            # Tip must itself be a convert from this markdown. Edits must not
            # inherit derived_from=md (save(..., from_convert=False) strips that).
            if tip.derived_from != row.id:
                return (
                    f"Error: {out_name} already has edits (or was not produced "
                    f"from {row.name}). Converting would overwrite the tip. "
                    "Use edit_docx on the current tip, or choose a new output name."
                )
            parent_id = tip.id

        data = build_docx(
            markdown,
            title=(title or "").strip(),
            author=(author or "").strip(),
            theme=(theme or "").strip() or None,
            toc=bool(toc),
            page_numbers=bool(page_numbers),
            rtl=bool(rtl),
        )

        try:
            saved = await files.save(
                user_id,
                name=out_name,
                data=data,
                content_type=DOCX_MEDIA_TYPE,
                parent_id=parent_id,
                derived_from=row.id,
                from_convert=True,
            )
        except FileTooLargeError as exc:
            return f"Error: {exc}"

        edit_bit = ""
        if notes:
            edit_bit = " Edits: " + "; ".join(notes) + "."
        return (
            f"Converted {row.name} → {saved.name} ({saved.size} bytes) "
            f"on the server (body not regenerated by the model).{edit_bit} "
            f"Download: /api/files/{saved.id}/download"
        )
