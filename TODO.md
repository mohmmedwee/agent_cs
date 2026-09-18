# cleverso-ai — roadmap

Living checklist so we do not lose the thread. Check items off as they ship.
Last agreed sequence: **PDF read + auto-title → XLSX export → run_python → branching**.

---

## Now (in progress)

- [x] **PDF reading** — `pypdf` in file read path; per-page text; cite page numbers in search
- [x] **Auto-title** — refine chat title after first exchange via cheap upstream call
- [x] **XLSX export** — `openpyxl` via `repositories/spreadsheets.py`; `write_file` builds real `.xlsx`
- [x] **`run_python` sandbox** — temp cwd, stripped env, wall-clock + soft memory cap; register output files; HITL

## Next

- [ ] **PDF export** — if still needed
- [ ] **Per-tool approval policy** — `always` / `ask` / `never` (python stays ask-by-default)
- [ ] **Regenerate last answer** — optional model/effort override
- [ ] **Usage logging** — prompt/completion tokens, latency, model, steps (feeds admin + compact tuning)

## Later (high payoff, bigger scope)

- [ ] **Artifacts / canvas pane** — finish `ArtifactContext` (HTML/MD/code + sandboxed preview)
- [ ] **RAG over uploads** — pgvector + chunks + LM Studio embeddings + `search_documents`
- [ ] **MCP client** — discover/register remote tools into `ToolRegistry`
- [ ] **Scheduled / recurring runs** — ticker + `ScheduledRun`; results as new conversations
- [ ] **Shareable read-only links** — signed `/share/{token}` (after production auth)
- [ ] **Prompt library** — user-saved prompts with `{{variables}}`
- [ ] **Keyboard-first** — ⌘K palette, ⌘↵ send, Esc stop
- [ ] **Voice in/out** — Whisper + TTS (Arabic mobile priority)

## Done (recent)

- [x] Auth, server-backed chats, Cleverso UI, real `.docx`
- [x] Tools: search, fetch, files, write_file + HITL
- [x] User memory + Memory page
- [x] Context summarization (DB: `context_summary` / `summarized_count`)
- [x] Background chat jobs + browser done notification
- [x] Runaway repetition cutoff
- [x] Levantine dialect guidance
- [x] Chat calm: answer before thinking; collapse finished tools
- [x] PDF reading for uploads + page cites in search
- [x] Auto-title refine after first exchange
- [x] XLSX export from Markdown tables / CSV via write_file
- [x] `run_python` sandbox (HITL + temp cwd + timeout; register outputs)

## Explicitly deferred

- Full marketing redesign (stay on Cleverso tokens)
- Multi-agent planner mode (not needed yet)
- RAG before PDF/read gaps are closed
- Conversation branching (edit stays in-place rewind; no fork/switcher)

## Notes

- HITL is in-memory today — multi-worker needs Redis (part of production hardening).
- `CONTEXT_OVERHEAD_TOKENS ≈ 2500` is a guess until usage logging exists.
- Prefer extending existing seams (`FileRepository`, `documents.py`, `ChatJobBroker`, `ApprovalBroker`) over new frameworks.
