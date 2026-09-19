---
name: docx
description: "Use this skill whenever the user wants to create, edit, or polish a Word document (.docx). Triggers: Word doc, .docx, report, memo, letter, proposal, or any polished downloadable document with headings, tables, or branding. Prefer this over inventing npm/pandoc workflows."
license: Proprietary. LICENSE.txt has complete terms
---

# Word documents in this product

Do **not** use npm `docx`, pandoc, LibreOffice scripts, or the helper scripts under
this skill's `scripts/` folder. Those assume Claude Code's shell and are not how
documents are produced here.

## Creating a new DOCX

1. Call `read_skill` with `docx` when the user wants a polished Word doc.
2. **Which file?** If they say "update the doc" and more than one upload could
   match, call `list_uploaded_files`, then `ask_user` with the file names as
   options — do not pick at random.
3. **Look & colors?** If they want a restyle without naming colors/theme, call
   `ask_user` with 2–4 options before converting.
4. **Uploaded Markdown/text** (especially long reports): `convert_upload_to_docx`.
   Do **not** `read_uploaded_file` the whole body and re-emit through `write_file`.
5. **Markdown content updates:** `convert_upload_to_docx` with small
   `replacements` / `sections` — never rewrite the entire file.
6. **New short content from scratch:** `write_file` with a `.docx` name.

## Editing an existing DOCX (required path)

Once a `.docx` tip exists, edit it with **`edit_docx`**. Do not reconvert.
Do not silently fall back to `rewrite`, `run_python`, or `write_file`.

### Workflow

1. `search_uploaded_files` (optional) to locate the phrase / section.
2. `read_uploaded_file` — DOCX lines are annotated as `[gN:p_#### h=…]`.
3. Copy **IDs and hashes exactly** as shown. Temp IDs for inserts are `new_1`,
   `new_2`, … — never generation-prefixed (`new_1`, not `g1:new_1`).
4. Batch related changes into **one** `edit_docx` call.
5. Retry at most **twice** after a fixable error, then ask the user.

### Choosing an operation

| Op | When | Notes |
| --- | --- | --- |
| `replace` | Small change | Include enough surrounding words in `old` to make it unique in that block. Prefer spans that sit inside one run. |
| `rewrite` | Whole paragraph must change | Requires `hash`. On mixed-formatting paragraphs needs `allow_format_loss` — set **only after the user agrees**. |
| `insert` | New paragraphs | Chain with `new_id=new_1` then `relative_to=new_1`. |
| `delete` | Remove a paragraph | Requires `hash`. |

### Errors → what to do

| Error | Response |
| --- | --- |
| Generation mismatch | Re-read the document, retry with fresh IDs |
| Stale hash | Re-read that block |
| Ambiguous `old` | Add surrounding context to `old` |
| `old` not found | Re-read the block; text may have changed |
| `multi_run_span` | Try a shorter `old` that sits inside one run and is still unique (e.g. `01-01` instead of the full date). If that fails, ask the user — do **not** rewrite |
| Field / revision rejection | Explain (e.g. "this paragraph has tracked changes; accept or reject them in Word first") |

### Boundaries

- **`run_python`** only for things `edit_docx` cannot do: headers, footers, images,
  charts, complex layout. It invalidates all block IDs — re-read afterwards.
- Never reconvert an edited DOCX chain to "fix" text.
- Never invent IDs or hashes; always copy from the annotated read.

### Worked patterns

**Replace (preferred):**

```text
edit_docx name=report.docx generation=1
operations:
  - op: replace
    block_id: g1:p_0012
    old: "Status: Draft"
    new: "Status: Final"
```

**Insert chain:**

```text
edit_docx name=report.docx generation=1
operations:
  - op: insert
    relative_to: g1:p_0003
    position: after
    content: "## Findings"
    new_id: new_1
  - op: insert
    relative_to: new_1
    position: after
    content: "Summary of the review."
    new_id: new_2
```

## convert_upload_to_docx (Markdown → DOCX only)

### Convert only (theme / toc)

```text
source: report.md
theme: cleverso
toc: true
page_numbers: true
```

### Update Markdown without rewriting the whole file

```text
source: report.md
theme: cleverso
replacements:
  - find: "Status: Draft"
    replace: "Status: Final"
```

## write_file (new / short content only)

```markdown
---
title: Solution Design Document
theme: cleverso
author: Cleverso
toc: true
page_numbers: true
---

# Overview

Short purpose paragraph.
```

## Themes

| Theme | When |
| --- | --- |
| `cleverso` | Cleverso / product / branded docs |
| `classic` | Formal reports |
| `modern` | Specs, technical notes |
| `warm` | Guides, onboarding |
| `editorial` | Neutral default |

## After writing

Tell the user the file name; the UI shows the download card. Do not paste the
full document into chat.
