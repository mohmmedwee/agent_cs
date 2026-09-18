---
name: docx
description: "Use this skill whenever the user wants to create, edit, or polish a Word document (.docx). Triggers: Word doc, .docx, report, memo, letter, proposal, or any polished downloadable document with headings, tables, or branding. Prefer this over inventing npm/pandoc workflows — this product builds .docx from Markdown via convert_upload_to_docx or write_file."
license: Proprietary. LICENSE.txt has complete terms
---

# Word documents in this product

Do **not** use npm `docx`, pandoc, LibreOffice scripts, or the helper scripts under
this skill's `scripts/` folder. Those assume Claude Code's shell and are not how
documents are produced here.

## Required workflow

1. Call `read_skill` with `docx` (this file) when the user wants a polished Word doc.
2. **Which file?** If they say "update the doc" / "that report" and more than one
   upload could match, call `list_uploaded_files`, then `ask_user` with the file
   names as clickable options — do not pick a version at random.
3. **Look & colors?** If they want a restyle / theme / "make it branded" without
   naming colors or a theme, call `ask_user` with 2–4 options (e.g. cleverso /
   classic / modern, or their brand colors) before converting.
4. **Uploaded Markdown/text already exists** (especially long reports): call
   `convert_upload_to_docx`. Do **not** `read_uploaded_file` the whole body and
   re-emit it through `write_file` — that OOMs local models on large files.
5. **Content updates on a Markdown/text upload:** use `convert_upload_to_docx`
   with small `replacements` and/or `sections` — never rewrite the entire file.
   If they did not provide the new wording, ask for it first.
6. **Content updates on an existing .docx only** (no `.md` source):
   - Prefer `run_python` + `python-docx` to edit the uploaded `.docx` in place
     (open it, change the table/section, save a new name). Stage the file with
     `inputs`. Do **not** paste the whole document into a giant `write_file`.
   - If the doc is short and you already have the full text from a prior read,
     `write_file` a new `.docx` from Markdown is OK — keep it one call, then stop.
7. **New content from scratch** (short): use `write_file` with a `.docx` name.
8. Use `run_python` only when the tools above cannot cover the edit (charts,
   complex table surgery, in-place `.docx` patches).

**Do not** spend the turn debating which tool is allowed. Pick one path, call
the tool, and finish.

## convert_upload_to_docx

### Convert only (theme / toc)

```text
source: Alignment_Test_Cases_Report_GlobalSearch.md
theme: cleverso
toc: true
page_numbers: true
```

### Update content without rewriting the whole file

**Find/replace snippets:**

```text
source: report.md
theme: cleverso
replacements:
  - find: "Status: Draft"
    replace: "Status: Final"
```

**Rewrite one section** (heading match is case-insensitive / substring):

```text
source: report.md
theme: cleverso
sections:
  - heading: "TC-02"
    content: |
      Updated findings for this test case only…
```

If you need several sections changed, call the tool once per section (or pass
multiple `sections` entries), each with only that section's new Markdown.

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

Table **headers** use the theme accent color with white bold text.

## After writing

Tell the user the file name; the UI shows the download card. Do not paste the
full document into chat.
