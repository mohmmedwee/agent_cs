# DOCX editing (`edit_docx`)

Living plan for the server-side DOCX edit tool. Cursor plan mirror:
`~/.cursor/plans/edit-docx_refactor_d8acdfa3.plan.md`.

| Phase | Status |
| --- | --- |
| Quick wins (strict convert, search offsets, version chain + tip CAS) | **Done** |
| Phase 1 — Foundation | **Done** (awaiting soak data from real use) |
| Phase 2 — Formatting preservation | Not started |
| Phase 3 — Tracked changes + polish | Not started |

---

## Phase 1 — Done when (all met)

- Same-generation insert-then-edit keeps IDs; convert / `run_python` rebuild → old ids rejected with re-read.
- `next_id` survives delete of highest block.
- Concurrent double Allow → one win, one stale CAS.
- Stale hash / apply revalidation / identical-`rPr` merge / `multi_run_span` / table cells / field+revision reject / approval plaintext.
- Skill + system prompt prefer `edit_docx`; no silent `write_file` / reconvert.
- Fixed e2e corpus (sanitized fixtures) + live regression runner.
- **Soak logging** (`agent_console.docx_soak`): operations summary, error types, retries, denied approvals, fallbacks to `run_python` / `write_file` / `convert_upload_to_docx`.

### Soak (post-ship)

Use Phase 1 on real work. Collect `docx_soak` log lines. When there is enough volume, bring pass/fail and error-type counts back to order Phase 2.

E2E stability: `EDIT_DOCX_E2E=1 EDIT_DOCX_E2E_ROUNDS=5 uv run python scripts/run_edit_docx_e2e.py` → pass rates in `tests/fixtures/edit_docx_e2e/stability.json` (committed). Full event transcripts stay gitignored.

---

## Phase 2 — Formatting preservation

The main job is the **run-offset mapper**: map character spans in a paragraph to specific OOXML run pieces so replacements keep surrounding formatting.

Also in this phase:

| Item | Notes |
| --- | --- |
| Full run-offset mapper | Cross-run / mixed-`rPr` replaces without `multi_run_span` rejects |
| `replace_all` | Server-side change X→Y throughout; no LLM |
| Table / row / cell hierarchy | Beyond flat cell `w:p` blocks |
| **Lists and styles on insert** | Preserve list numbering and paragraph styles when inserting |
| **Narrower field / revision safety** | From whole-paragraph reject → overlapping-range only |
| **Content-control refinement** | SDT contents as normal editable blocks (gov templates) |
| Arabic normalize + offset map | Loose find, exact write; golden set |

### Done when

An Arabic paragraph with mixed bold text and a hyperlink can be edited mid-sentence, and everything outside the edited words looks exactly as before when opened in Word.

Order Phase 2 work from soak data, not from this table alone.

---

## Phase 3 — Tracked changes + polish

- Richer approval UI if needed.
- Word revisions; **platform-author revisions editable, human revisions blocked**.
- Formatting-loss notes on rewrite.

---

## Deliberately out of scope

No embeddings/RAG for DOCX edit, no PDF write-back, no separate planner service.
