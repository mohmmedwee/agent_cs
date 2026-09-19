# cleverso-ai — feature plan

This is the index. Each feature has a full build spec in `plan/`, covering:
- what the user gets and how the code works today, with file:line references;
- the design decisions and why;
- a file-by-file change list;
- numbered build steps with code (signatures, SQL, component props);
- i18n keys in both languages, tests, a manual test plan, and a "done when" checklist.

**Read `plan/00-foundation.md` first.** The repo has no test setup yet, and every feature ends with tests.

| # | Feature | Spec | Size | Backend | Migration | New deps |
|---|---|---|---|---|---|---|
| 00 | Test foundation | [plan/00-foundation.md](plan/00-foundation.md) | ~1 h | config only | – | pytest, vitest (dev) |
| F1 | Regenerate answer | [plan/F1-regenerate.md](plan/F1-regenerate.md) | S · ½–1 d | none | – | – |
| F2 | Real PDF + PowerPoint output | [plan/F2-pdf-pptx-output.md](plan/F2-pdf-pptx-output.md) | M · 3–4 d | yes | – | `python-pptx`, LibreOffice |
| F3 | Workspace canvas (HTML/MD/code/CSV/SVG) | [plan/F3-workspace-canvas.md](plan/F3-workspace-canvas.md) | M · 2–3 d | small | – | – |
| F4 | Search across uploads (RAG) | [plan/F4-rag-search.md](plan/F4-rag-search.md) | L · 6–8 d | yes | yes | pgvector, embedding model |
| F5 | Saved prompts with `{{variables}}` | [plan/F5-saved-prompts.md](plan/F5-saved-prompts.md) | M · 2–3 d | yes | yes | – |
| F6 | Voice input | [plan/F6-voice-input.md](plan/F6-voice-input.md) | S–M · 1–2 d | none | – | – |
| F7 | Scheduled runs (Automations) | [plan/F7-scheduled-runs.md](plan/F7-scheduled-runs.md) | L · 6–8 d | yes | yes | – |
| — | DOCX `edit_docx` (Phase 1 done; soak → Phase 2) | [plan/edit-docx.md](plan/edit-docx.md) | L | yes | yes | – |

## Milestones (build order)

1. **M0:** `00-foundation`.
2. **M1, quick wins:** F1 + F3. Frontend-heavy, no migrations. F3 also fixes the round-5 bug where English
   documents render right-aligned in the Arabic UI.
3. **M2, deliverables:** F2. Needs LibreOffice on the server (`/usr/local/bin/soffice` locally) and Arabic fonts
   on Linux.
4. **M3, knowledge:** F4. **Confirm the prerequisites first:** the `vector` extension in Postgres, and an
   embedding model (`bge-m3`) loaded in LM Studio.
5. **M4, productivity:** F5 + F6.
6. **M5, automation:** F7, in two PRs: first the `start_chat_run` refactor with a snapshot test, then the feature.

## Migration chain
The current head is `d4e5f6a7b8c9` (user_skills). New revisions chain in build order:
`e5f6a7b8c9d0` (F4 file_chunks) → `f6a7b8c9d0e1` (F5 saved_prompts) → `a7b8c9d0e1f2` (F7 automations).
If features ship in a different order, set each `down_revision` to whatever is the head at that time.

## Ground rules (every feature)
- **Reuse the existing seams**:
  - `ToolRegistry` / `ToolContext` for tools (tools are auto-discovered from `services/tools/`);
  - `FileRepository` for stored files;
  - `ChatJobBroker` + `ApprovalBroker` for runs;
  - `ConversationRepository` for messages;
  - the memory CRUD stack (`models → repositories → schemas → routes → dependencies`) as the template for new
    CRUD;
  - `useArtifact()` for the workspace.
- **Every user-owned row** has `user_id` with `ondelete="CASCADE"`, and every query is scoped by `user_id`.
  Another user's id → 404 (never 403, which would leak that the id exists).
- **Bilingual + RTL:**
  - every visible string goes in both `frontend/src/i18n/en.json` and `ar.json`, with full Arabic plural forms
    where there's a count;
  - logical CSS only (`ps/pe/ms/me/start/end`);
  - generated files (PDF/PPTX) render Arabic RTL.
- **Design system:** Quiet Workbench tokens (`task.md` §2): `ink*`, `paper*`, `line`, `violet-*`. No
  `secondary-*`. Icons go in `components/Icons.tsx` (24×24, stroke 1.75). No emoji.
- **Accessibility:** real buttons, `aria-label` on icon buttons, visible focus, 36px hit targets, keyboard paths
  for every menu and dialog.
- **Model-facing text** (tool descriptions, system notes) stays short. The model reads it on every step.
- **Before calling a feature done:** `scripts/check.sh` (ruff, pytest, frontend build + lint + vitest), with no
  new lint warnings over the current 25, and the feature's manual test plan in EN/AR and light/dark.
- **Agents (Cursor/Claude) never commit or push** unless the user asks.

## Out of scope for this plan
- Usage/token logging and admin analytics (track separately; it also unblocks tuning `CONTEXT_OVERHEAD_TOKENS`).
- Server-side Whisper (F6 v2), RAG reranking and OCR (F4 "Later"), syntax highlighting (F3 v1).
- Sharing conversations/prompts between users; multi-worker HITL via Redis.
- The open `run_python` security fixes in `fixes.md` (#1, #2, #5). They're **not features**, but they should
  land before F7, because F7 lets `run_python` run without a human watching.
