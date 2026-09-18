# Code review — fixes

Two-axis review (`/code-review`) with the `codebase-design` "deep modules" lens folded into the Standards axis.

- **Fixed point (baseline):** `50fe5fb` — reviewing everything since, i.e. 4 commits (`ca3c03d`, `4a03703`, `c6c362c`, `29303a3`) **plus** current uncommitted/untracked work.
- **Spec source:** `TODO.md` roadmap (agreed sequence *PDF read + auto-title → XLSX export → run_python → branching*). No issue tracker / `CODING_STANDARDS.md` exist.
- **Tooling baseline (skipped in review):** ruff `select = [E, F, I, UP, B, SIM]`, line-length 100 — import order, unused imports, line length, f-string upgrades, and simple bugbear/simplify are tooling-owned and not reported.
- **Method:** two parallel sub-agents, one per axis, so their contexts don't cross-contaminate. Axes are reported **separately and not reranked** — a change can pass one axis and fail the other. Parent verified the top backend findings (#1, #3/#5 gate, #11) against source before writing this file.

---

## Standards

*Scope note: tooling-owned trivia excluded per the ruff baseline. Everything below is either a real correctness/security bug or a Fowler/deep-module judgement call, marked as such. Files ordered by descending worst severity.*

### `src/agent_console/services/tools/run_python.py`

**1. Output collection reads whole files into memory before the size gate — OOM/DoS**
- **Severity:** High · **Type:** Correctness/Bug (resource exhaustion)
- **Location:** `run_python.py:210-226` (`data = path.read_bytes()`, then `files.save(...)`); size check lives downstream in `files.py:60`.
- **Why:** The child can write an arbitrarily large file to its cwd. The parent does `path.read_bytes()` (whole file into RAM) *before* `FileRepository.save` compares against `max_upload_bytes`. A single `open("big","wb").write(b"0"*20_000_000_000)` makes the server load 20 GB into memory. The `RLIMIT_AS` child cap does not constrain bytes written to disk. *(Verified: `files.py:60` gates on `len(data)` after the full read.)*
- **Fix:** Guard on `path.stat().st_size` (and total staged bytes) against `settings.max_upload_bytes` *before* reading:
  ```python
  if path.stat().st_size > settings.max_upload_bytes:
      errors.append(f"{path.name}: {path.stat().st_size} bytes exceeds limit")
      continue
  data = path.read_bytes()
  ```

**2. Output walk follows symlinks and has no per-file size/type guard — arbitrary-file exfil + traversal/hang**
- **Severity:** Medium · **Type:** Security
- **Location:** `run_python.py:203-209` (`cwd.rglob("*")` + `path.is_file()`); `_is_user_output` at `run_python.py:62-77`.
- **Why:** `is_file()` follows symlinks and `_is_user_output` only screens on names. A script doing `os.symlink("/etc/passwd", "out.txt")` gets that target read and saved into the durable, downloadable store; `rglob` can traverse a symlinked directory tree and hang.
- **Fix:** Use `os.walk(cwd, followlinks=False)`, skip `path.is_symlink()`, and confirm `path.resolve().is_relative_to(cwd.resolve())` before saving.

**3. Subprocess runs as the server user with full filesystem + inherited `PATH` and no network block**
- **Severity:** High · **Type:** Security (partially documented)
- **Location:** `run_python.py:171-180` (`create_subprocess_exec`), env at `154-169` (`"PATH": os.environ.get("PATH", ...)`), docstring lines 1-9.
- **Why:** Env is stripped (good — no `SECRET_KEY`/`DATABASE_URL`), but the child runs with the API process's uid and unrestricted filesystem access, so it can read `PROJECT_ROOT/.env`, the upload store, or anything the server user can, and print it back. `PATH` is inherited so it can `exec` host binaries; network is not OS-blocked. HITL is the only real control, and the approval card shows opaque code.
- **Fix:** Acknowledged as "pragmatic, not a hardened jail," so treat as a design gate: run under a dedicated unprivileged uid inside a container/`nsjail`/`bwrap` with read-only rootfs, bind-mounted scratch, `--net none`, CPU/PIDs limits. At minimum drop `PATH` to a minimal value and document the trust boundary at the tool interface, not just a docstring.
- **Design (interface):** Otherwise a reasonably deep module (small `run_python(code, inputs)` surface), but its interface silently carries huge unenforced invariants ("no network", "isolated"). Encode the guarantees you enforce; make the ones you don't explicit to callers.

**4. `RLIMIT_AS` memory cap is a silent no-op off Linux**
- **Severity:** Low · **Type:** Design:interface (documented)
- **Location:** `run_python.py:40-54` (`_runner_source`), config `python_memory_bytes`.
- **Why:** On macOS (the `darwin` dev target) `RLIMIT_AS` is generally not enforced, and the runner swallows failure in `except Exception: pass`. The advertised "memory cap" is absent on the dev platform; only wall-clock timeout is real there.
- **Fix:** Fine to keep, but log once when the cap can't be applied, and don't let the config field imply a guarantee it doesn't provide.

### `src/agent_console/services/agent.py`

**5. HITL approval gate is silently skipped when `conversation_id` is falsy**
- **Severity:** High · **Type:** Security
- **Location:** `agent.py:249-252` — `if (conversation_id and name in self._settings.approval_required_tools):`
- **Why:** The allow/deny gate for `write_file`/`run_python` is conditional on an unrelated optional parameter. Any caller of `AgentService.run(...)` that omits `conversation_id` (defaults to `None`) executes approval-required tools — including `run_python` — with no gate. A security control shouldn't couple to an optional routing argument. *(Verified against source.)*
- **Fix:** Fail closed. If a tool is in `approval_required_tools` and there's no way to obtain approval, **deny** rather than run:
  ```python
  if name in self._settings.approval_required_tools:
      if not conversation_id:
          result = "Error: this tool requires approval, which is unavailable in this context."
          yield ToolResultEvent(id=call_id, name=name, result=result)
          continue
      yield ToolApprovalEvent(...); allowed = await self._approvals.wait(...)
  ```

**6. Upstream streaming generator isn't closed on early `break` — held httpx connection**
- **Severity:** Medium · **Type:** Correctness/Bug (resource leak)
- **Location:** `agent.py:173-198` (breaks at 189 and 197-198); generator `UpstreamClient.stream_completion` wraps `async with self._http.stream(...)` (`upstream.py:174-204`).
- **Why:** Breaking out of `async for chunk in chunks` suspends the async generator; its `async with self._http.stream` `__aexit__` doesn't run until GC, so the upstream connection stays open. Under load this leaks pool connections.
- **Fix:** Wrap the stream in `contextlib.aclosing`:
  ```python
  from contextlib import aclosing
  async with aclosing(self._upstream.stream_completion(...)) as chunks:
      async for chunk in chunks: ...
  ```

**7. Runaway detection is O(n²) over the whole stream**
- **Severity:** Low · **Type:** Design:testability/perf (judgement)
- **Location:** `agent.py:174-177` calls `is_runaway_repetition("".join(streamed_text))` per delta; `runaway.py:13-24` scans the full string each call.
- **Why:** Re-joining and full-scanning per delta is quadratic. Bounded by `max_completion_tokens`, so not catastrophic, but wasteful on the hot path (also duplicated on the client, see #18).
- **Fix:** Track a running same-char count and only re-check the trailing window (`joined[-256:]`) per delta.

### `src/agent_console/repositories/conversations.py` (+ schema + migration + model)

**8. Conversation branching is fully built but wired to nothing — speculative generality**
- **Severity:** Medium · **Type:** Smell:Speculative Generality (judgement)
- **Location:** `conversations.py:114-196` (`_root_id`, `fork_from`, `list_family`); `schemas/conversations.py:84-85` (`BranchListResponse`, exported but unused); `db/models.py:55-61` (`parent_id`, `branched_at_position`); `migrations/versions/c3d4e5f6a7b8_conversation_branching.py`; `frontend/src/types.ts:64`.
- **Why:** No route calls `fork_from`/`list_family`, no endpoint returns `BranchListResponse`. An entire feature — repo methods, Pydantic response, DB migration/columns, frontend type — ships with no caller, adding untested risk surface (`fork_from` copies all messages, `_root_id` walks a parent chain). *(This is also the Spec axis's headline scope-creep finding — see Spec #5.)*
- **Fix:** Either land the endpoint that uses these, or delete `fork_from`/`list_family`/`_root_id`/`BranchListResponse` now. Don't leave untested dead paths in the repo.

**9. `_root_id` cycle guard is subtly incomplete**
- **Severity:** Low · **Type:** Correctness/Bug (judgement; only matters if #8 is wired up)
- **Location:** `conversations.py:114-124`.
- **Why:** `seen` records `current.id` before stepping to the parent, but the loop checks `current.parent_id not in seen`. The "root has null parent" invariant is assumed, not enforced; a mis-set `parent_id` chain could surprise.
- **Fix:** Guard on visiting the *next* id (`if parent.id in seen: break`) and cap depth.

### `src/agent_console/repositories/files.py`

**10. `raw_bytes` / `text` load entire files into memory on every call**
- **Severity:** Medium · **Type:** Design:interface / resource (judgement)
- **Location:** `files.py:113-115` (`raw_bytes`), `123-135` (`text`), `137-159` (`read_text`).
- **Why:** Every download, preview, docx-media fetch, and `run_python` input staging calls `read_bytes()` on the whole file. Bounded by `max_upload_bytes = 10 MB`, but the download route (`routes/files.py:136`) buffers the full file per request; with #1 it's the OOM mechanism. The interface offers no streaming seam.
- **Fix:** Add a streaming accessor (`open_stream`) and use `StreamingResponse`/`FileResponse` for downloads; keep `raw_bytes` for small in-process transforms only.

**11. `FileRepository.__init__` performs disk I/O (mkdir) as a side effect**
- **Severity:** Low · **Type:** Design:testability (judgement)
- **Location:** `files.py:48-52` (`self._directory.mkdir(parents=True, exist_ok=True)`). *(Verified.)*
- **Why:** Constructing the repo (per request in the chat producer, `routes/chat.py:120`) touches the filesystem, so it can't be unit-constructed without a real directory, and repeats the mkdir every request. "Accept dependencies, don't create them" — the directory is already created at startup in `main.py:61-62`.
- **Fix:** Drop the `mkdir` from `__init__`; rely on the startup `upload_dir.mkdir(...)`.

### `src/agent_console/services/chat_jobs.py`

**12. Unbounded per-job replay buffer**
- **Severity:** Medium · **Type:** Design:interface / resource (judgement)
- **Location:** `chat_jobs.py:16-24` (`events: list`), `37-47` (`publish` appends every event).
- **Why:** Every streamed event (each `text_delta`/`reasoning_delta`) is retained in `job.events` for the life of the run to support reconnect replay. A long reasoning run holds the entire token stream in memory per active conversation. No cap/trimming in the interface.
- **Fix:** Cap the buffer (ring buffer of last N, or coalesce text deltas into a running string for replay) and document the reconnect-fidelity trade-off.

**13. Job dropped immediately on completion contradicts its own comment**
- **Severity:** Low · **Type:** Correctness/Bug (minor UX)
- **Location:** `chat_jobs.py:90-98` — comment says "Keep briefly so late watchers can see is_active flip" but `_clear` calls `self._jobs.pop(...)` synchronously.
- **Why:** A `watch`/`active` request just after completion gets 404 and misses terminal events, despite the stated intent to linger.
- **Fix:** Keep a short-lived tombstone (done job retained a few seconds) or update the comment to match immediate-drop.

### `src/agent_console/services/context_compact.py`

**14. Dead fallback branch + coupled summary fields**
- **Severity:** Low · **Type:** Smell:Speculative Generality / Data Clumps (judgement)
- **Location:** dead branch at `context_compact.py:160` (`fold = remainder[:-keep] if keep < len(remainder) else remainder[:-1]`) — the `else` is unreachable because `156-158` already returns when `len(remainder) <= keep`. Data clump: `(context_summary, summarized_count)` travel together across `db/models.py:64-65`, `schemas/conversations.py:60-76`, `conversations.py:152-162`, and this module.
- **Why:** The `else remainder[:-1]` can never execute; the summary/count pair is passed as two loose primitives everywhere, inviting drift (`fork_from` already hand-reconciles them).
- **Fix:** Delete the dead branch (`fold = remainder[:-keep]`). Consider a small `RollingSummary(text, covered_count)` value object holding the "covered ≤ keep" invariant in one place.

### `src/agent_console/services/auto_title.py` / `context_compact.py` / `upstream.py`

**15. Repeated one-shot completion + error-handling shape**
- **Severity:** Low · **Type:** Smell:Duplicated Code (judgement)
- **Location:** `auto_title.py:64-73`, `context_compact.py:165-174` — both `model or await upstream.resolve_model()` then `complete_text(...)` inside `except (UpstreamError, httpx.HTTPError, KeyError)`; `list_models` in `routes/chat.py:374-378` catches a near-identical set.
- **Why:** Same "resolve-model, best-effort single completion, swallow the same three exceptions, log-and-skip" shape in two services — the kind of thing that drifts.
- **Fix:** Extract `upstream.best_effort_text(prompt, model, ...)` owning model resolution + exception contract, returning `str | None`.

### `src/agent_console/repositories/documents.py`

**16. Deep module — good — but a large, partly redundant interface**
- **Severity:** Nit · **Type:** Design:interface (judgement, mostly praise)
- **Location:** `documents.py:1065-1074` (`build_docx` signature); front-matter overlap at `1085-1088`.
- **Why:** Genuinely **deep**: enormous Markdown→OOXML behaviour behind `build_docx(markdown, ...) -> bytes`, testable via bytes in/out — a model to keep. Wrinkle: `title`/`author`/`theme` are accepted both as kwargs *and* parsed from YAML front matter, and `toc`/`page_numbers`/`base_dir`/`images`/`rtl` widen the surface.
- **Fix:** Optional — collapse document-level options into one `DocxOptions` dataclass and define one precedence rule (arg overrides front matter) in one spot. No behavioural change.

### `frontend/src/lib/chatRunner.ts`

**17. Module-global mutable state + `??`-as-statement**
- **Severity:** Low · **Type:** Design:testability / Standard (judgement)
- **Location:** globals `runs`/`waiters`/`queryClient`/`notifyCopy` (`chatRunner.ts:42-47, 98`); control-flow abuse at `82-88` (`waiters.get(id)?.add(wrapper) ?? waiters.set(id, new Set([wrapper]))`).
- **Why:** The runner deliberately survives unmount (the feature), but via module singletons + a globally-bound `queryClient`, so it can only be tested by mutating hidden module state. The `?? set(...)` uses nullish-coalescing purely for a side effect (reads as a bug); the `wrapper`/`pending` indirection is a pass-through (Middle Man).
- **Fix:** Replace `??` with explicit `if (!waiters.has(id)) waiters.set(id, new Set()); waiters.get(id)!.add(listener)`. Drop the `wrapper`/`pending` alias. Longer term, encapsulate the store in a class instance injected at bind time so it's mockable.

**18. O(n²) runaway check + array rebuilds on every delta**
- **Severity:** Low · **Type:** Correctness/perf (judgement)
- **Location:** `chatRunner.ts:117-133` (`appendDelta` runs `isRunawayRepetition(nextText)` on full accumulated text per delta) + `patchBlocks` rebuilding arrays each delta.
- **Why:** For long replies this re-scans the whole message per token on the main thread, allocating new `turns`/`blocks` arrays and (via the hook, #19) re-serializing. Noticeable jank on long streams.
- **Fix:** Only scan the trailing window; consider mutating a ref + throttled `emit` rather than full immutable rebuilds per delta.

### `frontend/src/hooks/useChat.ts`

**19. `getSnapshot` does `JSON.stringify` of the last turn on every store read**
- **Severity:** Low · **Type:** Design:testability/perf (judgement)
- **Location:** `useChat.ts:48-58` (`useSyncExternalStore` snapshot builds `...:${JSON.stringify(snap.turns[snap.turns.length - 1])}`).
- **Why:** Serializes the last turn (all blocks/text for an assistant turn) on every render/emit. Correct (equal primitive, no tearing), but heavy work tied to render frequency, compounding #18.
- **Fix:** Have the runner expose a monotonically increasing `version: number` per run; use that as the snapshot; drop the `JSON.stringify`.

### Cross-cutting

**20. Runaway logic duplicated across backend and frontend**
- **Severity:** Low · **Type:** Smell:Duplicated Code / Shotgun Surgery risk (judgement)
- **Location:** `src/agent_console/services/runaway.py` and `frontend/src/lib/runaway.ts` implement the same `_CHAR_RUN`/`_UNIT_REPEATS` (64/24) algorithm.
- **Why:** Both runtimes legitimately need it, but the thresholds/algorithm must stay in lockstep; a change to one is a scattered edit across languages with no shared test. Drift means the client trims differently than the server persists.
- **Fix:** Accept the duplication but pin it: cross-reference comment in both files + a shared test vector (same inputs → same trimmed output) so drift is caught.

### Notably solid (no action)
- `ApprovalBroker` (`approvals.py`) — deep, tiny interface, dependencies injected, honestly documented single-node limitation.
- `ConversationRepository` ownership scoping (`user_id` filter in the repo, not routes) and `FileRepository.get`'s id-then-name lookup correctly reject cross-user ids.
- `extraction.docx_media_bytes` path handling (`extraction.py:199-201`) properly blocks traversal.
- `context.py` `ToolContext` is a clean seam for per-request, user-scoped tool wiring; keeps tools constructible in tests.

---

## Spec

### (a) Missing / Partial — none

All four `## Now (in progress)` checked items are genuinely and fully implemented (verified against source; listed so the roadmap can close them out).

**1. PDF reading — VERIFIED conformant (no action)**
- **Spec line:** `- [x] PDF reading — pypdf in file read path; per-page text; cite page numbers in search`
- **Evidence:** `extraction.py:222` `from pypdf import PdfReader`; per-page markers `extraction.py:241` `sections.append(f"--- Page {index} ---\n{body}")`; routed in `extract_text` `extraction.py:254`; page cites in search `search_files.py:69-70` (`page = page_at_offset(...)` → `where = f"page {page}, offset {position}"`).

**2. Auto-title — VERIFIED conformant (no action)**
- **Spec line:** `- [x] Auto-title — refine chat title after first exchange via cheap upstream call`
- **Evidence:** `auto_title.py:44` `if len(messages) != 2: return` (exactly first user+assistant exchange); cheap call `auto_title.py:66-71` (`complete_text ... max_tokens=40`); wired in the chat producer's `finally` `routes/chat.py:192` `await maybe_refine_title(...)`. Skips if user already renamed.

**3. XLSX export — VERIFIED conformant (no action)**
- **Spec line:** `- [x] XLSX export — openpyxl via repositories/spreadsheets.py; write_file builds real .xlsx`
- **Evidence:** `spreadsheets.py:167` `from openpyxl import Workbook` → real bytes `spreadsheets.py:223-225` (`wb.save(buffer)`); `write_file` routes `.xlsx` at `write_file.py:73`. Markdown tables → sheets, CSV → one sheet, prose → Notes. Real workbook, not text-as-xlsx.

**4. `run_python` sandbox — VERIFIED conformant (no action)**
- **Spec line:** `- [x] run_python sandbox — temp cwd, stripped env, wall-clock + soft memory cap; register output files; HITL`
- **Evidence (`run_python.py`):** temp cwd `:134`; stripped env (whitelist dict, not `os.environ`) `:155-169`; wall-clock timeout `:184-186` + killpg; **soft** memory cap `:50` `resource.setrlimit(resource.RLIMIT_AS, (_cap, _hard))`; register outputs `:213-218`; HITL via `config.py:150` `approval_required_tools` default `{"write_file", "run_python"}` gated in `agent.py:249-261`.
- **Note:** All six sub-requirements present. *(Standards axis separately flags security weaknesses in this same file — see Standards #1–#4; spec-conformance and hardening are different axes.)*

### (b) Scope creep

**5. Conversation branching is being implemented despite being explicitly deferred (headline finding)**
- **Spec line:** `- Conversation branching (edit stays in-place rewind; no fork/switcher)` (under `## Explicitly deferred`), reinforced by `Last agreed sequence: ... run_python → branching` (branching is the next, not-yet-authorized step).
- **Evidence:**
  - **Live DB migration (alembic head)** — `migrations/versions/c3d4e5f6a7b8_conversation_branching.py:22-42`: adds `parent_id`, `branched_at_position`, self-FK `fk_conversations_parent_id`, index `ix_conversations_parent_id`. It is the head revision (`down_revision = "b2c3d4e5f6a7"`, nothing revises from it), so `alembic upgrade head` applies branching schema to production.
  - **Model columns** — `db/models.py:53-61`, incl. comment `# ... so the branch switcher stays a flat family list.`
  - **Repo fork logic** — `conversations.py:126` `async def fork_from(...)`, `:183` `async def list_family(...)`, `:114` `_root_id`.
  - **Schema** — `schemas/conversations.py:84-85` `BranchListResponse`; `:50-51` `parent_id`/`branched_at_position` on `ConversationSummary`.
  - **Frontend types** — `frontend/src/types.ts:63-64` `parent_id`/`branched_at_position`.
- **Severity:** **Blocker** (the migration ships schema for a feature the spec says MUST NOT be implemented); **High** for the model/repo/schema/type code.
- **Fix:** Revert the branching migration and the `fork_from`/`list_family`/`_root_id` methods, `BranchListResponse`, and the `parent_id`/`branched_at_position` model+schema+type fields. Keep only in-place rewind — the rewind path (`truncate_from` `conversations.py:89` + `/rewind` route `api/routes/conversations.py:70`) is intact and honors the spec; leave that.

**6. Branching is dark scaffolding (not exposed) — narrows blast radius, still scope creep**
- **Spec line:** `- Conversation branching (... no fork/switcher)`
- **Evidence:** No route exposes `fork_from`/`list_family`; `BranchListResponse` is unused by any router; `ChatSessionBar.tsx` is a context/status footer (session status + token meter + summary popover), **not** a branch switcher. Feature is backend + migration only, no user-facing switcher yet.
- **Severity:** Medium (triage context).
- **Fix:** Because nothing calls it, removal is low-risk — half-built deferred work, not a wired feature. Remove rather than gate.

**7. Out-of-sequence "Later" work: Artifacts/canvas groundwork**
- **Spec line:** `- [ ] Artifacts / canvas pane — finish ArtifactContext (HTML/MD/code + sandboxed preview)` (under `## Later` — not in the agreed current sequence).
- **Evidence:** new `frontend/src/components/chat/ArtifactContext.tsx` (Artifact provider with open/close preview state), plus new `DocumentPreview.tsx`, `DocxNativePreview.tsx`, `XlsxNativePreview.tsx`.
- **Severity:** Low.
- **Fix:** Not on the MUST-NOT list, but "Later" work landing ahead of the agreed sequence. Flag for confirmation; no spec violation, just scope drift.

**Marketing redesign / multi-agent planner / RAG — NOT present (confirmed).** Grep for `pgvector|embedding|vector|rag|planner|multi-agent|ScheduledRun|search_documents` returns only `TODO.md` text and unrelated matches. UI changes (`Logo.tsx`, `AuthLayout.tsx`, `styles.css`) stay on Cleverso tokens — no redesign.

### (c) Wrong — none functional
- The `db/models.py:54` comment `so the branch switcher stays a flat family list` contradicts "no fork/switcher", but that's intent-of-scope-creep evidence (covered by #5), not a separately incorrect implementation. The rewind requirement itself is implemented correctly.

---

## Summary

- **Standards:** 20 findings (2 High — #1 OOM/DoS, #3 & #5 security; 1 more High-equivalent security gate; several Medium; rest Low/Nit judgement calls) + 4 items flagged as notably solid. **Worst within axis:** the `run_python` security posture and the fail-open HITL gate (#1, #3, #5) — real correctness/security, not judgement calls.
- **Spec:** 4 in-progress items fully verified; **1 Blocker** scope-creep. **Worst within axis:** #5 — explicitly-deferred **Conversation branching** shipping as the live alembic head migration plus repo/schema/model/type scaffolding.

*(The two axes are reported separately by design; no single cross-axis "winner" is chosen — that's the reranking the separation exists to prevent.)*
