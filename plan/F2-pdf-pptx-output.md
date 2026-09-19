# F2 — Real PDF and PowerPoint output

**Size:** M (3–4 days) · **Backend:** yes · **Migration:** none · **New deps:** `python-pptx`, LibreOffice
(system) · **Depends on:** 00-foundation

## What the user gets
"Make it a PDF" or "turn this into a 6-slide deck" produces a real `.pdf` / `.pptx` in one `write_file` call,
with no `run_python` approval prompt. Arabic comes out right-to-left and correctly shaped in both formats. Charts
the agent made earlier with `run_python` can be embedded in either.

## Current state
- `src/agent_console/services/tools/write_file.py:20`: `_UNSUPPORTED = {".pdf", ".doc", ".xls", ".ppt",
  ".pptx", ".odt", ".rtf"}` refuses these formats.
- `.docx` → `build_docx(content)` (`repositories/documents.py:1095`). It has themes (`_THEMES`: `editorial`,
  `cleverso`, …), front matter (`title`, `theme`, `toc`, `pages`, `rtl`), per-paragraph RTL detection
  (`_is_rtl`), tables, images (`images: dict[src, bytes]` or http/data URLs), and page numbers.
- `write_file` calls `build_docx(content)` with **no images dict**, so a Markdown image pointing at an earlier
  output (`/api/files/<id>/download`) isn't embedded today. This spec fixes that for docx, pdf and pptx at once.
- The frontend already previews `.pptx` (`PptxNativePreview.tsx`, via `@aiden0z/pptx-renderer`) and badges PPT.
- `soffice` exists at `/usr/local/bin/soffice` on the dev machine.

## Design decisions
1. **PDF = Markdown → `build_docx` → LibreOffice `--convert-to pdf`.** It reuses every docx feature (themes,
   RTL, tables, images, TOC, page numbers), so PDF and DOCX always match. Pure-Python PDF libraries would need
   manual Arabic shaping and bidi and a second layout engine.
2. **PPTX = our own Markdown → slides builder on `python-pptx`, drawing on the blank layout.** The default
   python-pptx template is 4:3 with placeholders positioned for 4:3. Drawing our own text boxes on a 16:9 blank
   slide gives full control of theme, RTL and overflow.
3. **Images by file link.** Any Markdown image whose src is `/api/files/<uuid>/download` (the link format every
   tool already returns) is loaded from the user's `FileRepository` and passed in as bytes.

## Files

| File | Change |
|---|---|
| `pyproject.toml` | add `python-pptx>=1.0` |
| `src/agent_console/config.py` | `soffice_path`, `pdf_convert_timeout`, `pdf_max_concurrency` |
| `src/agent_console/repositories/markdown_blocks.py` | **new**: shared pure helpers moved out of `documents.py` |
| `src/agent_console/repositories/documents.py` | import those helpers (no behavior change) |
| `src/agent_console/repositories/pdf.py` | **new**: `docx_to_pdf()` |
| `src/agent_console/repositories/presentations.py` | **new**: `build_pptx()` |
| `src/agent_console/services/tools/file_images.py` | **new**: resolve `/api/files/<id>/download` images |
| `src/agent_console/services/tools/write_file.py` | `.pdf` / `.pptx` branches, images, new description |
| `skills/writing-deliverables/SKILL.md`, `skills/pdf/SKILL.md`, `skills/pptx/SKILL.md` | prefer `write_file` |
| `src/agent_console/api/routes/files.py` | `?inline=1` on download (for the PDF preview) |
| `frontend/src/components/chat/DocumentPreview.tsx` | PDF preview, PPT badge colors, rank |
| `frontend/src/pages/ChatPage.tsx` | auto-open rank includes pdf |
| `tests/test_markdown_blocks.py`, `tests/test_presentations.py`, `tests/test_pdf.py`, `tests/test_write_file.py` | **new** |

---

## Step 1: move the shared Markdown helpers (pure refactor)

Create `repositories/markdown_blocks.py` and **move** these from `documents.py` unchanged, dropping the leading
underscore: `_front_matter` → `front_matter`, `_truthy` → `truthy`, `_is_rtl` → `is_rtl` (with its
`_RTL_CHARS` regex), `_table_cells` → `table_cells`, `_alignments` → `alignments`.

In `documents.py`, replace the definitions with:

```python
from agent_console.repositories.markdown_blocks import (
    alignments as _alignments,
    front_matter as _front_matter,
    is_rtl as _is_rtl,
    table_cells as _table_cells,
    truthy as _truthy,
)
```

This way no call site inside `documents.py` changes. Run the app and generate a .docx to confirm nothing moved.

`tests/test_markdown_blocks.py`: `front_matter` with/without a block and with an unterminated block;
`is_rtl("مرحبا Kubernetes")` is True, `is_rtl("Hello مرحبا world again")` is False; `table_cells` with an escaped
pipe; `alignments("|:--|:-:|--:|")` → `["", "center", "right"]`.

## Step 2: config

```python
# --- document export ---------------------------------------------------
soffice_path: str | None = Field(
    default=None,
    description="LibreOffice binary for PDF export. Auto-detected on PATH when unset.",
)
pdf_convert_timeout: float = Field(default=60.0, gt=0)
pdf_max_concurrency: int = Field(default=2, ge=1, le=8)
```

## Step 3: `repositories/pdf.py`

```python
"""PDF export by converting our own .docx with headless LibreOffice.

One document pipeline (Markdown → docx) serves both formats, so a PDF looks
exactly like the Word file, Arabic shaping and all.
"""

import asyncio
import shutil
import tempfile
from pathlib import Path

from agent_console.config import Settings

__all__ = ["PDF_MEDIA_TYPE", "PdfConversionError", "PdfUnavailableError", "docx_to_pdf"]

PDF_MEDIA_TYPE = "application/pdf"

_slots: asyncio.Semaphore | None = None


class PdfUnavailableError(RuntimeError):
    """LibreOffice is not installed or not configured."""


class PdfConversionError(RuntimeError):
    """LibreOffice ran but did not produce a PDF."""


def _binary(settings: Settings) -> str:
    found = settings.soffice_path or shutil.which("soffice") or shutil.which("libreoffice")
    if not found:
        raise PdfUnavailableError("LibreOffice (soffice) is not installed on this server")
    return found


async def docx_to_pdf(docx: bytes, settings: Settings) -> bytes:
    global _slots
    if _slots is None:
        _slots = asyncio.Semaphore(settings.pdf_max_concurrency)
    binary = _binary(settings)

    async with _slots:
        with tempfile.TemporaryDirectory(prefix="pdf-") as tmp:
            work = Path(tmp)
            source = work / "document.docx"
            source.write_bytes(docx)
            # A private profile per call: two concurrent soffice processes that
            # share the default profile fail with "user installation locked".
            profile = (work / "profile").as_uri()
            process = await asyncio.create_subprocess_exec(
                binary, "--headless", "--norestore", "--nolockcheck",
                f"-env:UserInstallation={profile}",
                "--convert-to", "pdf", "--outdir", str(work), str(source),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            try:
                _, stderr = await asyncio.wait_for(
                    process.communicate(), timeout=settings.pdf_convert_timeout
                )
            except TimeoutError as exc:
                process.kill()
                await process.wait()
                raise PdfConversionError("PDF conversion timed out") from exc

            output = work / "document.pdf"
            if process.returncode != 0 or not output.exists():
                detail = stderr.decode("utf-8", "replace").strip()[-400:]
                raise PdfConversionError(f"LibreOffice failed: {detail or 'no output'}")
            return output.read_bytes()
```

**Fonts:** Arabic PDFs need an Arabic font on the server. On macOS the system fonts cover it. On Linux or
Docker, install `fonts-noto-core fonts-noto-ui-core` (or `fonts-noto-kufi-arabic`). Put this in the README
deployment notes.

## Step 4: `repositories/presentations.py`

### Markdown convention (this text goes into the tool description too)

```
---
title: Q3 review            # optional; overrides the first H1 as the deck title
subtitle: Board update       # optional
theme: cleverso              # same names as docx themes
rtl: true                    # optional; force RTL for every slide
---
# Deck title                 → title slide (first H1 only)
Optional subtitle line       → first paragraph after the H1 = subtitle
## Slide title               → starts a content slide
- point / 1. point           → bullets (indent 2 spaces per level, max 3 levels)
Plain paragraph              → body text
| a | b |                    → native table (one per slide)
![caption](/api/files/<id>/download)   → picture (one per slide; laid out beside the bullets, or full width alone)
> notes: what to say        → speaker notes (all "> notes:" lines on a slide are joined)
```

### Data model and parser

```python
from dataclasses import dataclass, field

@dataclass
class Bullet:
    text: str
    level: int = 0          # 0..2
    ordered: bool = False

@dataclass
class Slide:
    title: str
    bullets: list[Bullet] = field(default_factory=list)
    paragraphs: list[str] = field(default_factory=list)
    table: tuple[list[str], list[list[str]]] | None = None
    image: tuple[str, str] | None = None   # (src, caption)
    notes: list[str] = field(default_factory=list)

@dataclass
class Deck:
    title: str
    subtitle: str
    slides: list[Slide]
```

`parse_deck(markdown: str) -> Deck`, line by line:
- `front_matter()` first. `# ` (first one) → deck title, and the next non-empty non-heading line → subtitle
  (unless front matter has one). Later `# ` lines are treated as `## `.
- `## ` → push a new `Slide`. Content before any `##` (other than the H1/subtitle) goes on an untitled first
  content slide.
- `-`, `*`, `+` or `\d+[.)]` with leading spaces → `Bullet(level=min(indent // 2, 2))`.
- A table block: a header row, then an `alignments` rule row, then body rows → `slide.table` (reuse
  `table_cells`).
- `![caption](src)` alone on a line → `slide.image`.
- `> notes:` → `slide.notes`. Other `>` lines become body paragraphs.
- Inline Markdown in text: strip `**`, `*`, `` ` `` markers but keep bold runs (see rendering). Links become
  their label.

### Overflow rule
After parsing, split any slide with **> 8 bullets or > 90 words** of bullet+paragraph text into consecutive slides
titled `"<title> (cont.)"`. Split at bullet boundaries only. Tables with > 8 body rows split the same way (the
header repeats).

### Rendering

```python
from io import BytesIO
from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.util import Emu, Inches, Pt

PPTX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.presentationml.presentation"
W, H = Inches(13.333), Inches(7.5)            # 16:9
MARGIN = Inches(0.6)

def build_pptx(markdown: str, *, images: dict[str, bytes] | None = None) -> bytes:
    deck = split_overflow(parse_deck(markdown))
    _, meta = front_matter(markdown)
    theme = _resolve_theme(meta.get("theme"))          # import from documents.py
    force_rtl = truthy(meta.get("rtl"))
    prs = Presentation()
    prs.slide_width, prs.slide_height = W, H
    blank = prs.slide_layouts[6]

    _title_slide(prs.slides.add_slide(blank), deck, theme, force_rtl)
    for slide in deck.slides:
        _content_slide(prs.slides.add_slide(blank), slide, theme, force_rtl, images or {})

    out = BytesIO()
    prs.save(out)
    return out.getvalue()
```

Rendering rules:
- **Colors/fonts from `_DocTheme`**: `ink` for text, `accent` for the title bar rule, `muted` for subtitles and
  captions, `heading_font` / `body_font`. Convert with `RGBColor.from_string(theme.ink)`.
- **Title slide:** title 40pt bold, vertically centered, with the subtitle 20pt `muted` below it and a 4pt
  `accent` bar above the title.
- **Content slide:** title 28pt bold in a text box at the top (`MARGIN`, height 0.9in), a thin `rule`-colored
  line under it, and a body area below.
  - Bullets: `text_frame.word_wrap = True`, 20pt at level 0, 18pt at level 1, 16pt at level 2,
    `paragraph.level = bullet.level`, 6pt space after. Ordered bullets are prefixed `"1. "` and so on, since
    python-pptx has no simple auto-numbering API.
  - Paragraphs: 18pt.
  - With an image, the body takes the left 55% and the image the right 40% (mirrored when RTL), fit inside its
    box keeping the aspect ratio (`_image_size` from `documents.py` gives the pixel size). Without an image,
    the body is full width.
  - Table: `shapes.add_table(rows, cols, …)`, header row filled with `accent` and white bold text, body rows
    14pt, column widths equal. Header cells follow `alignments`.
  - Notes: `slide.notes_slide.notes_text_frame.text = "\n".join(slide.notes)`.
- **RTL:** a paragraph is RTL if `force_rtl or is_rtl(text)`. For each such paragraph:

```python
def _rtl(paragraph) -> None:
    pPr = paragraph._p.get_or_add_pPr()
    pPr.set("rtl", "1")
    pPr.set("algn", "r")
```

  In RTL runs, set the complex-script font too, or PowerPoint falls back badly:

```python
from pptx.oxml.ns import qn
def _cs_font(run, name: str) -> None:
    rPr = run._r.get_or_add_rPr()
    cs = rPr.find(qn("a:cs"))
    if cs is None:  # not `or`: an lxml element with no children is falsy
        cs = rPr.makeelement(qn("a:cs"), {})
        rPr.append(cs)
    cs.set("typeface", name)
```

  Use `"Arial"` as the Arabic complex-script font (present on Windows, macOS and Office for Mac; Noto Kufi
  isn't guaranteed on the viewer's machine). When a slide's title is RTL, the image goes on the left.
- **Bold runs:** split text on `**…**` and set `run.font.bold = True` for the inner parts.

## Step 5: `services/tools/file_images.py`

```python
"""Load images a Markdown document references by their download link.

Every tool reports outputs as `/api/files/<id>/download`, so a chart made by
run_python can be dropped into a docx/pdf/pptx by that link.
"""

import re
from uuid import UUID

from agent_console.repositories.files import FileRepository, UnknownFileError

_LINK = re.compile(r"!\[[^\]]*\]\((/api/files/([0-9a-fA-F-]{36})/download)\)")


async def referenced_images(markdown: str, files: FileRepository, user_id: UUID) -> dict[str, bytes]:
    found: dict[str, bytes] = {}
    for src, file_id in _LINK.findall(markdown):
        if src in found:
            continue
        try:
            row = await files.get(user_id, file_id)
            if row.is_image:
                found[src] = await files.raw_bytes(user_id, file_id)
        except UnknownFileError:
            continue
    return found
```

(`FileRepository.get` accepts the id as a string ref, per `files.py:111`.) It's scoped by `user_id`, so one user
can't embed another user's file.

## Step 6: `write_file.py`

```python
_UNSUPPORTED = {".doc", ".xls", ".ppt", ".odt", ".rtf"}

...
images = await referenced_images(content, files, user_id)
if suffix == ".docx":
    data, content_type = build_docx(content, images=images), DOCX_MEDIA_TYPE
elif suffix == ".pdf":
    try:
        data = await docx_to_pdf(build_docx(content, images=images), context.settings)
    except PdfUnavailableError:
        return ("Error: PDF export isn't available on this server. "
                "Offer the user a .docx instead and call this tool again.")
    except PdfConversionError as exc:
        return f"Error: {exc}. Offer a .docx instead."
    content_type = PDF_MEDIA_TYPE
elif suffix == ".pptx":
    data, content_type = build_pptx(content, images=images), PPTX_MEDIA_TYPE
elif suffix == ".xlsx":
    ...
```

`build_docx` is CPU work (zip + XML) and `build_pptx` too. For large inputs, run them with
`await asyncio.to_thread(build_pptx, content, images=images)` so the event loop keeps streaming other chats.
Do the same for docx.

New tool description (replace the current one; keep it tight, since the model reads it every turn):

> Save content as a file the user can download. Write the content as Markdown. `.docx` → Word document;
> `.pdf` → PDF with the same layout as .docx; `.pptx` → slide deck (`# Title` = title slide, each `## Heading`
> = one slide, bullets/tables/one image per slide, `> notes:` = speaker notes); `.xlsx` → Markdown tables or
> CSV become sheets. Embed earlier images with `![caption](/api/files/<id>/download)`. Other extensions are
> plain text. If they uploaded a document and want it as .docx, use `convert_upload_to_docx`. If they give no
> data, invent a small realistic sample. Returns the download link.

## Step 7: skills
- `skills/writing-deliverables/SKILL.md`: under formats, add that **pdf and pptx go through `write_file`**,
  with the slide convention above and a short example deck.
- `skills/pdf/SKILL.md` and `skills/pptx/SKILL.md`: add at the top: "For documents/decks written from
  Markdown, call `write_file` with `.pdf`/`.pptx`. Use `run_python` only for editing an existing PDF/PPTX,
  filling forms, or merging/splitting."

## Step 8: download route: inline PDF

`routes/files.py` `download_file`: accept `inline: bool = False` (query). Use inline disposition when
`inline or content_type startswith "image/"`. That's needed for the iframe preview.

## Step 9: frontend
- `DocumentPreview.tsx`:
  - `isPdfFileName(name)` helper next to `isDocxFileName`.
  - In `ArtifactPanel`, add PDF to the "no text fetch" list in the effect (~L488), and render
    ```tsx
    {tab === 'preview' && isPdf ? (
      <iframe
        title={artifact.name}
        src={`${api.files.downloadUrl(artifact.fileId)}?inline=1`}
        className="h-full min-h-[70vh] w-full rounded bg-white"
      />
    ) : null}
    ```
    and exclude `isPdf` from the text-preview branch.
  - `fileBadgeClass`: PPT/PPTX `bg-[#FDF0E6] text-[#C2410C] dark:bg-[#431407] dark:text-[#FDBA74]`. PDF already
    has `bg-[#FDECEC] text-[#B42318]`; confirm the dark variant exists.
  - `badgeShort`: `PDF`, `PPT`.
- `ChatPage.tsx` `rank()` (~L424): `.pdf` → 1.5, i.e. between xlsx and pptx (use integers: docx 0, xlsx 1,
  pdf 2, pptx 3, images 4, other 6, json 9).

## Tests
`tests/test_presentations.py` (pure, opens the result with `Presentation(BytesIO(data))`):
- first `#` becomes the title slide; `##` count = content slide count;
- nested bullets get `paragraph.level` 0/1/2;
- a table produces a shape with `has_table` and the right row/column count;
- `> notes:` text is in `notes_slide`;
- an Arabic bullet has `rtl="1"` on its `a:pPr`;
- 12 bullets → 2 slides, the second titled "… (cont.)";
- an image src present in `images` produces a picture shape, and a missing one is skipped without crashing.

`tests/test_pdf.py`:
- `@pytest.mark.soffice`: converting `build_docx("# Hello\n\nمرحبا")` returns bytes starting with `b"%PDF"`;
- monkeypatch `shutil.which` → None and `soffice_path=None` → `PdfUnavailableError`;
- `pdf_convert_timeout=0.001` with soffice present → `PdfConversionError`.

`tests/test_write_file.py` (a fake `FileRepository` that records `save` calls):
- `.pdf` with soffice missing returns the friendly error and saves nothing;
- `.pptx` saves with `PPTX_MEDIA_TYPE`;
- `.ppt` is still refused;
- an image link to a file of **another** user isn't embedded.

## Manual test plan
1. "Make a 5-slide deck in Arabic about renewable energy in Jordan." The .pptx opens in Keynote/PowerPoint:
   RTL, readable, no overflow, and it previews in the workspace.
2. "Plot monthly sales as a chart and put it in a 3-slide deck." It calls `run_python` (approve), then
   `write_file` .pptx with the chart on a slide.
3. "Now save the report as PDF." The PDF matches the .docx, Arabic is shaped, and it previews inline.
4. Stop LibreOffice from being found (`SOFFICE_PATH=/nope`): the model gets the friendly error and offers a .docx.

## Done when
- [ ] All tests above pass; `scripts/check.sh` is green.
- [ ] Manual test plan 1–4 passes.
- [ ] README has the LibreOffice + font note.
