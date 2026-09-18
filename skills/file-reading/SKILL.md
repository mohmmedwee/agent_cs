---
name: file-reading
description: "Route how to read an uploaded file by type. Use when the user uploaded a file and its content is not yet in context, asks about an upload you have not read, or names a file (pdf, docx, xlsx, csv, json, image, zip, …). Do not use when the file text is already in context."
---

# Reading uploaded files

Uploads live in this product's file store. You see names via
`list_uploaded_files` — **not** the bytes. Read with the right tool for the
type; do not treat every file as plain text.

## Protocol

1. **Extension is the dispatch key.** Unknown → `list_uploaded_files` then decide.
2. **Read only what answers the question.** Prefer search or a small sample
   over slurping a huge file into context (everything you read is re-sent on
   later steps).
3. **For grounded Q&A over readable docs**, also follow `working-with-documents`
   (search before full read; page through windows; quote when precision matters).

## Dispatch

| Extension | First move |
| --- | --- |
| `.pdf` | `read_uploaded_file` — pages marked `--- Page N ---`. Cite pages. Scanned PDFs with no text: say so; use `view_image` only if a page was exported as an image. |
| `.docx` | `read_uploaded_file` (text/tables as text). For chart/image questions inside the Word file, ask the user to export the figure or use the PNG if they also uploaded it. |
| `.xlsx` / `.csv` / `.tsv` | Prefer `run_python`: sample with `openpyxl` `read_only=True` or `csv`/`pandas` `nrows=5`. Do not dump a whole large sheet into chat. `read_uploaded_file` works for CSV/TSV text; xlsx is not plain text — use Python. |
| `.json` / `.jsonl` | `read_uploaded_file` with a small window, or `run_python` to inspect structure (`json.load`, first lines of jsonl). |
| `.png` `.jpg` `.jpeg` `.gif` `.webp` | `view_image` with a **specific** question (transcribe, describe chart, read error). Do not `read_uploaded_file` images. |
| `.md` `.txt` `.log` code | `read_uploaded_file`. Large logs: search or read the end via offsets / targeted questions. |
| `.zip` / archives | Tell the user this server does not unpack archives yet; ask for the inner file uploaded separately. |
| `.pptx` `.xls` `.doc` other binaries | Say the format is not readable here; offer `.docx` / `.xlsx` / PDF / CSV instead (or convert via `run_python` only if a library is available). |

## Tool map (this product)

- `list_uploaded_files` — inventory
- `search_uploaded_files` — find a term + offsets (readable text files)
- `read_uploaded_file` — text / docx / pdf windows (`offset` to continue)
- `view_image` — vision Q&A on images
- `run_python` — structured sampling (xlsx, csv shape, json), needs Allow/Deny

## Failure modes

- Treating a PDF/docx/xlsx as something to "cat" or invent content for
- Loading an entire CSV/xlsx when five rows would answer
- Using `read_uploaded_file` on an image instead of `view_image`
- Summarising a truncated `read_uploaded_file` window as the whole file
