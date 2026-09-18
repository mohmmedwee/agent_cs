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
2. **Uploaded Markdown/text already exists** (especially long reports): call
   `convert_upload_to_docx`. Do **not** `read_uploaded_file` the whole body and
   re-emit it through `write_file` — that OOMs local models on large files.
3. **Content updates on an upload:** still use `convert_upload_to_docx`, with
   small `replacements` and/or `sections` — never rewrite the entire file.
4. **New content from scratch** (short): use `write_file` with a `.docx` name.
5. Use `run_python` only for rare cases those tools cannot cover.

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
