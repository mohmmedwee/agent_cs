# F7 — Scheduled runs ("Automations")

**Size:** L (6–8 days) · **Backend:** yes · **Migration:** yes · **Depends on:** 00-foundation; F5 is optional
(inserting saved prompts into the editor)

## What the user gets
An **Automations** page: "Every weekday at 08:30, search the news about X and write a one-page brief as a
.docx." Each run happens on its own, even with the browser closed, and lands as a **new conversation** marked
unread in the chat list. It also sends a browser notification if the app is open. Each automation card shows the
next run, the last result, Run now, Pause, Edit and Delete.

## Current state (what we build on)
- `POST /api/chat` (`api/routes/chat.py:64–230`) does everything inline:
  - loads the conversation, builds the `history`, appends the user message, and calls `prepare_model_messages`;
  - defines `produce()`, which owns its own session and builds `FileRepository`, `MemoryRepository`,
    `UserSkillRepository`, `SkillCatalog`, `build_registry(ToolContext(...))` and `AgentService`;
  - streams `agent.run(...)` events into `blocks`/`text_parts` via `_collect` and `jobs.publish`, then persists
    the assistant message and runs `maybe_refine_title`;
  - `jobs.spawn(key, produce(), cancel)`, then returns SSE.
- `ChatJobBroker` (in memory) handles `spawn/register/stop/is_active/publish/subscribe`, with a tombstone replay
  window.
- `ApprovalBroker.wait(conversation_id, call_id, timeout)` blocks until the user answers, or times out as deny.
  `AgentService.run(..., auto_approve_tools=set(...))` skips the gate for listed tools (`agent.py:411`).
- `lib/notify.ts` + `chatRunner` already notify when a run finishes, but only for runs the browser started.

## Design
1. **Refactor first (its own PR):** extract the body of `POST /api/chat` into
   `services/chat_runs.py:start_chat_run(...)`. The route becomes a thin wrapper, and the scheduler calls the
   same function. **Behavior must be byte-for-byte the same**, and a snapshot test guards it.
2. **Unattended mode.** `AgentService.run(..., unattended=True)`:
   - a gated tool **not** in `auto_approve_tools` is **denied immediately** (no waiting) with the result
     `"Error: this is a scheduled run with no one to approve <tool>. It is not allowed for this automation."`;
   - `ask_user` (choice prompts) returns `"Error: no one is available to answer. Make a sensible assumption,
     state it, and continue."`;
   - a system note is appended to the system prompt: "This is a scheduled, unattended run. Do not ask questions;
     finish the task and produce the deliverable."
3. **Scheduler loop** in the app lifespan: every 30 s, claim due automations with
   `FOR UPDATE SKIP LOCKED` (safe with several workers), advance `next_run_at` **in the same transaction**
   (so a crash can't double-run), then start the run. Missed runs (server was down) run **once** on startup if
   they're less than 6 hours late, and are skipped otherwise.
4. **Recurrence** is structured JSON, not cron. It's easier to validate and to show in both languages:
   ```json
   {"kind": "daily",    "time": "08:30"}
   {"kind": "weekdays", "time": "08:30"}                 // Mon–Fri
   {"kind": "weekly",   "time": "09:00", "days": [1, 4]} // ISO weekday 1=Mon … 7=Sun
   {"kind": "monthly",  "time": "09:00", "day": 31}      // 31 → last day in shorter months
   ```
   Plus an IANA `timezone` (e.g. `Asia/Amman`). The next run is computed with `zoneinfo`, so DST is correct.
5. **Safety defaults.** The allowed tools default to read/search tools plus `write_file`. `run_python` is off
   unless ticked, with a warning. Max 20 automations per user. The minimum frequency is daily.

## Files

| File | Change |
|---|---|
| `src/agent_console/services/chat_runs.py` | **new**: `start_chat_run()` (moved from the route) |
| `src/agent_console/api/routes/chat.py` | `POST /chat` calls `start_chat_run` |
| `src/agent_console/services/agent.py` | `unattended` flag |
| `src/agent_console/services/tools/ask_user.py` | unattended behavior (via `ToolContext.unattended`) |
| `src/agent_console/services/tools/context.py` | `unattended: bool = False` |
| `migrations/versions/a7b8c9d0e1f2_automations.py` | **new** |
| `src/agent_console/db/models.py` | `Automation`; `Conversation.source/automation_id/unread` |
| `src/agent_console/services/recurrence.py` | **new** (pure) |
| `src/agent_console/repositories/automations.py` | **new** |
| `src/agent_console/services/scheduler.py` | **new** |
| `src/agent_console/schemas/automations.py`, `api/routes/automations.py` | **new** |
| `src/agent_console/schemas/conversations.py`, `api/routes/conversations.py` | `source`, `unread`, PATCH `unread` |
| `src/agent_console/main.py` | scheduler task; router |
| `src/agent_console/config.py` | scheduler settings |
| `frontend/src/pages/AutomationsPage.tsx` | **new** |
| `frontend/src/components/AutomationEditorDialog.tsx` | **new** |
| `frontend/src/lib/recurrence.ts` (+ test) | **new**: human-readable text + validation |
| `frontend/src/hooks/useAutomations.ts`, `lib/api.ts`, `types.ts` | client |
| `frontend/src/components/NavRail.tsx`, `App.tsx` | nav item + route |
| `frontend/src/components/ConversationList.tsx` | unread dot, clock icon; mark read on open |
| `frontend/src/components/Icons.tsx` | `ClockIcon` |
| `i18n` | keys below |

---

## Step 1: refactor `POST /api/chat` into `start_chat_run` (PR 1)

```python
# services/chat_runs.py
@dataclass(frozen=True)
class RunRequest:
    user_id: UUID
    conversation_id: UUID
    message: str
    model: str | None = None
    effort: str | None = None
    auto_approve_tools: frozenset[str] = frozenset()
    web_search: bool = False
    research: bool = False
    skill: str | None = None
    unattended: bool = False


async def start_chat_run(state, settings: Settings, upstream: UpstreamClient,
                         run: RunRequest, *,
                         on_finished: Callable[[str], Awaitable[None]] | None = None) -> str:
    """Append the user message, spawn the producer as a background job, return the job key.

    Raises UnknownConversationError. Shared by POST /api/chat and the scheduler.
    """
```

Move into it, unchanged: the `async with factory() as session:` block (load, history, append user, prepare
messages, commit), `blocks/text_parts/cancel`, the whole `produce()` closure, and `jobs.spawn(...)`. Replace
`request.X` with `run.X` and `http_request.app.state` with `state`. `_collect` and `_close_open_tools` move too
(keep them module-private). The route becomes:

```python
@router.post("/chat", response_model=None)
async def chat(request: ChatRequest, http_request: Request, user: CurrentUserDep,
               settings: SettingsDep, upstream: UpstreamClientDep) -> EventSourceResponse:
    try:
        key = await start_chat_run(http_request.app.state, settings, upstream, RunRequest(
            user_id=user.id, conversation_id=request.conversation_id, message=request.message,
            model=request.model, effort=request.effort,
            auto_approve_tools=frozenset(request.auto_approve_tools),
            web_search=request.web_search, research=request.research, skill=request.skill))
    except UnknownConversationError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    return _sse_from_job(http_request.app.state.chat_jobs, key)
```

`produce()` calls `on_finished(status)` at the very end of its `finally` (status `"ok"` if the agent loop ended
normally, `"failed"` if it raised, and `"cancelled"` on stop), wrapped in its own try/except so a callback error
never breaks persistence. The scheduler uses it to record the result. The route passes nothing.

**Regression test (write it BEFORE moving code, run it after):** `tests/test_chat_runs.py`, `@db`. Use a fake
`UpstreamClient` whose `stream_completion` yields a scripted sequence: reasoning → a `write_file` tool call →
final text. Run the old route through `httpx.AsyncClient(app=…)`, capture the stored assistant `blocks` +
`content`, and save them as a JSON snapshot. After the refactor, the same test must produce an identical snapshot.

## Step 2: unattended mode
- `ToolContext`: add `unattended: bool = False`. It's set from `run.unattended` where `produce()` builds the context.
- `AgentService.run(..., unattended: bool = False)`, at the approval gate (`agent.py:411`):
  ```python
  if name in self._settings.approval_required_tools and name not in skip_approval:
      if unattended:
          result = (f"Error: this is a scheduled run with no one to approve {name}. "
                    "It is not allowed for this automation; continue without it.")
          ...append tool message, continue...
      elif conversation_id:
          ...existing wait path...
  ```
- In the system prompt builder, when `unattended`, append:
  `"This is a scheduled, unattended run. Nobody will reply. Do not ask questions; make reasonable assumptions,
  state them briefly, and finish with the deliverable."`
- `tools/ask_user.py`: `if context.unattended: return "Error: no one is available to answer. …"`.

Test: with a fake upstream that calls `run_python` while `unattended=True` and `run_python` not auto-approved,
the tool result is the error string, there's no wait (the test finishes in < 1 s), and the run completes.

## Step 3: migration `a7b8c9d0e1f2_automations.py`

```python
op.create_table(
    "automations",
    sa.Column("id", UUID, primary_key=True),
    sa.Column("user_id", UUID, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
    sa.Column("title", sa.String(120), nullable=False),
    sa.Column("prompt", sa.Text, nullable=False),
    sa.Column("model", sa.String(200), nullable=True),
    sa.Column("effort", sa.String(16), nullable=True),
    sa.Column("web_search", sa.Boolean, server_default=sa.false(), nullable=False),
    sa.Column("allowed_tools", postgresql.JSONB, server_default=sa.text("'[]'::jsonb"), nullable=False),
    sa.Column("recurrence", postgresql.JSONB, nullable=False),
    sa.Column("timezone", sa.String(64), nullable=False),
    sa.Column("enabled", sa.Boolean, server_default=sa.true(), nullable=False),
    sa.Column("next_run_at", sa.DateTime(timezone=True), nullable=True),
    sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True),
    sa.Column("last_status", sa.String(16), nullable=True),       # ok | failed | skipped | running
    sa.Column("last_error", sa.String(400), nullable=True),
    sa.Column("last_conversation_id", UUID,
              sa.ForeignKey("conversations.id", ondelete="SET NULL"), nullable=True),
    sa.Column("created_at", …now()), sa.Column("updated_at", …now()),
)
op.create_index("ix_automations_user", "automations", ["user_id"])
op.create_index("ix_automations_due", "automations", ["enabled", "next_run_at"])

op.add_column("conversations", sa.Column("source", sa.String(16), server_default="chat", nullable=False))
op.add_column("conversations", sa.Column("automation_id", UUID,
              sa.ForeignKey("automations.id", ondelete="SET NULL"), nullable=True))
op.add_column("conversations", sa.Column("unread", sa.Boolean, server_default=sa.false(), nullable=False))
```

The downgrade reverses it in order (conversation columns first, then the indexes, then the table). Note the circular
FKs (automations → conversations → automations). Both are nullable with `SET NULL`, so creation order is: table
first, then conversation columns.

## Step 4: `services/recurrence.py` (pure)

```python
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

class RecurrenceError(ValueError): ...

def validate(rec: dict, tz: str) -> None:
    """kind in {daily, weekdays, weekly, monthly}; time HH:MM 00:00–23:59; weekly.days non-empty ⊂ 1..7;
    monthly.day 1..31; tz resolvable by ZoneInfo. Raise RecurrenceError with a user-facing message."""

def next_run(rec: dict, tz: str, after: datetime) -> datetime:
    """First occurrence strictly after `after` (aware UTC), returned as aware UTC."""
    zone = ZoneInfo(tz)
    local_after = after.astimezone(zone)
    hh, mm = map(int, rec["time"].split(":"))
    day = local_after.date()
    for _ in range(0, 400):                     # bounded: at most ~13 months ahead
        if _matches(rec, day):
            candidate = _at(day, time(hh, mm), zone)
            if candidate > local_after:
                return candidate.astimezone(ZoneInfo("UTC"))
        day += timedelta(days=1)
    raise RecurrenceError("no upcoming occurrence")

def _matches(rec, day: date) -> bool:
    kind = rec["kind"]
    if kind == "daily": return True
    if kind == "weekdays": return day.isoweekday() <= 5
    if kind == "weekly": return day.isoweekday() in rec["days"]
    if kind == "monthly":
        last = (day.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
        return day.day == min(rec["day"], last.day)

def _at(day: date, t: time, zone: ZoneInfo) -> datetime:
    """Local wall time → aware datetime, handling DST gaps and overlaps.
    Gap (e.g. 02:30 that doesn't exist): move forward to the first valid minute.
    Overlap (01:30 happens twice): take the first (fold=0)."""
    naive = datetime.combine(day, t)
    aware = naive.replace(tzinfo=zone, fold=0)
    # detect a gap: round-tripping through UTC changes the wall time
    roundtrip = aware.astimezone(ZoneInfo("UTC")).astimezone(zone)
    if roundtrip.replace(tzinfo=None) != naive:
        aware = roundtrip  # zoneinfo already shifted it past the gap
    return aware
```

Tests (`tests/test_recurrence.py`) with `after` values chosen around edges:
- daily: before and after today's time; weekdays: Friday evening → Monday; weekly `[1,4]` from Tuesday → Thursday;
- monthly day 31 from Feb 1 → Feb 28/29, and from Apr 30 23:59 → May 31;
- DST: `Europe/Berlin` 02:30 on the spring-forward date runs at 03:30 local; on the fall-back date 02:30 runs once;
  `Asia/Amman` (no DST since 2022) doesn't shift; `America/New_York` spring-forward;
- `validate` rejects `25:00`, `days: []`, `day: 0`, `tz: "Mars/Base"`.

## Step 5: repository + API
`repositories/automations.py`: `list_for`, `get`, `create` (validate + compute `next_run_at = next_run(rec, tz,
now)`; limit `max_automations=20` → `AutomationLimitError`), `update` (recompute `next_run_at` when recurrence,
tz or enabled changes), `delete`, `set_enabled`.

`schemas/automations.py`:
```python
class Recurrence(BaseModel):
    kind: Literal["daily", "weekdays", "weekly", "monthly"]
    time: str = Field(pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    days: list[int] | None = None
    day: int | None = Field(default=None, ge=1, le=31)

class AutomationIn(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    prompt: str = Field(min_length=1, max_length=8000)
    model: str | None = None
    effort: Effort | None = None
    web_search: bool = False
    allowed_tools: list[str] = Field(default_factory=list)
    recurrence: Recurrence
    timezone: str
    enabled: bool = True
```
Validate `allowed_tools` against `settings.approval_required_tools` (unknown names → 400).

`routes/automations.py` (`/api/automations`): `GET`, `POST` (201), `PATCH /{id}`, `DELETE /{id}` (204),
`POST /{id}/run-now` (202, starts immediately and doesn't change `next_run_at`, returns
`{conversation_id}`), `GET /tools` (the list of gated tools with a `dangerous: bool` flag, `run_python` = true,
for the editor checkboxes).

Conversations: `ConversationSummary` gains `source: str = "chat"`, `unread: bool = False` and
`automation_id: UUID | None`. `RenameConversationRequest` becomes `ConversationPatch(title: str | None, unread: bool |
None)` (keep accepting `{title}` so the current client keeps working).

## Step 6: `services/scheduler.py`

```python
class Scheduler:
    def __init__(self, state, settings, upstream) -> None: ...

    async def run_forever(self) -> None:
        await asyncio.sleep(5)                                  # let the app finish starting
        while True:
            try:
                await self._tick(utcnow())
            except Exception:
                logger.exception("scheduler tick failed")
            await asyncio.sleep(self._settings.scheduler_poll_seconds)   # 30

    async def _tick(self, now: datetime) -> None:
        async with self._factory() as session:
            due = (await session.execute(
                select(Automation)
                .where(Automation.enabled.is_(True), Automation.next_run_at <= now)
                .order_by(Automation.next_run_at)
                .limit(10)
                .with_for_update(skip_locked=True)
            )).scalars().all()
            starts: list[tuple[Automation, bool]] = []
            for auto in due:
                late = now - auto.next_run_at
                run_it = late <= timedelta(hours=6)
                auto.next_run_at = next_run(auto.recurrence, auto.timezone, now)   # advance FIRST
                if not run_it:
                    auto.last_status = "skipped"
                starts.append((auto, run_it))
            await session.commit()
        for auto, run_it in starts:
            if run_it:
                await self.start(auto.id)

    async def start(self, automation_id: UUID) -> UUID | None:
        """Create the conversation and start the run. Also used by run-now."""
        async with self._factory() as session:
            auto = await session.get(Automation, automation_id)
            if auto is None:
                return None
            if auto.last_conversation_id and self._jobs.is_active(str(auto.last_conversation_id)):
                auto.last_status = "skipped"; auto.last_error = "previous run still going"
                await session.commit(); return None
            conv = await ConversationRepository(session).create(
                auto.user_id, title=f"{auto.title} · {local_date(auto.timezone)}")
            conv.source, conv.automation_id, conv.unread = "schedule", auto.id, True
            auto.last_run_at, auto.last_status, auto.last_error = utcnow(), "running", None
            auto.last_conversation_id = conv.id
            await session.commit()
            conv_id = conv.id

        await start_chat_run(self._state, self._settings, self._upstream, RunRequest(
            user_id=auto.user_id, conversation_id=conv_id, message=auto.prompt,
            model=auto.model, effort=auto.effort, web_search=auto.web_search,
            auto_approve_tools=frozenset(auto.allowed_tools), unattended=True,
        ), on_finished=partial(self._record, automation_id))
        return conv_id

    async def _record(self, automation_id: UUID, status: str) -> None:
        async with self._factory() as session:
            auto = await session.get(Automation, automation_id)
            if auto:
                auto.last_status = "ok" if status == "ok" else "failed"
                await session.commit()
```

`local_date(tz)` formats today's date in the automation's timezone as `YYYY-MM-DD`. The chat title then gets
refined by auto-title as usual.

**Notification.** The scheduler publishes nothing to browsers directly. The frontend polls the conversation list
(step 7), and when an `unread` schedule conversation appears that wasn't in the previous list, it calls
`notifyChatDone` from `lib/notify.ts` with the automation title. That's only while a tab is open, which is
acceptable for v1.

**Config:** `scheduler_enabled: bool = True` (set false on extra workers), `scheduler_poll_seconds: float = 30`,
`max_automations: int = 20`, `automation_max_lateness_hours: float = 6`.

**`main.py` lifespan:** start `Scheduler(...).run_forever()` as a task when `scheduler_enabled`, and cancel it in
`finally` (the same pattern as the F4 indexer).

## Step 7: frontend

**Nav + route.** `NavRail.tsx`: add **Automations** (`ClockIcon`) after Skills. `App.tsx`: the `/automations`
route inside the shell. The mobile tab bar stays at 5 items: put Automations in the Settings page as a link row,
not in the bar.

**`lib/recurrence.ts`**
- `describeRecurrence(rec, t, locale): string`, e.g. "Every weekday at 08:30", "كل يوم إثنين وخميس الساعة
  09:00", "Monthly on day 31 (or the last day)". Build it from i18n keys; format weekday names with
  `Intl.DateTimeFormat(locale, { weekday: 'long' })` and time with `Intl.DateTimeFormat(locale, { hour:
  '2-digit', minute: '2-digit' })`.
- `validateRecurrence(rec)`, mirroring the backend rules, for inline form errors.
- Tests: every kind in `en` and `ar`, day-31 wording, and invalid inputs.

**`AutomationsPage.tsx`**: `PageHeader` (title, subtitle, "New automation" button), then a list of cards
(`.card`, `rounded-[14px]`):
- title (semibold, `dir="auto"`), `describeRecurrence` + timezone (`text-ink-2 text-[13px]`);
- "Next: in 3 h" (`Intl.RelativeTimeFormat`) or "Paused";
- a last-run status chip: ok = success tint, failed = error tint with the `last_error` tooltip, skipped =
  paper-3, running = violet with a spinner. The chip links to `/chat/{last_conversation_id}`;
- actions: an enable switch (`role="switch" aria-checked`), Run now (icon button; shows a spinner and then
  navigates to the new conversation), Edit, Delete (`ConfirmDialog`).
- Empty state: an illustration-free block with 3 example chips that prefill the editor ("Daily news brief",
  "Weekly report from my files", "Monday planning").

**`AutomationEditorDialog.tsx`** (dialog shell as in F5):
- Title; prompt (`textarea.field`, `dir="auto"`, 8 rows; if F5 exists, an "Insert saved prompt" link opens
  `PromptPicker`).
- Schedule: a kind segmented control (Daily / Weekdays / Weekly / Monthly), a time input (`type="time"`,
  `dir="ltr"`), day chips Mon–Sun for weekly (localized, starting on the locale's first day), a day-of-month
  number for monthly, a live preview line `describeRecurrence`, and "Next run: …" computed client-side for
  display only.
- Timezone: defaults to `Intl.DateTimeFormat().resolvedOptions().timeZone`, as a searchable select over
  `Intl.supportedValuesOf('timeZone')`.
- Model/effort: reuse `ModelEffortPicker` (default variant). Web search: a toggle.
- Allowed tools: checkboxes from `GET /api/automations/tools`. `write_file` is checked by default. `run_python`
  is unchecked and shows an inline warning (`automations.pythonWarning`) when ticked.
- Save → POST/PATCH; server 400 messages are shown inline.

**Conversation list** (`ConversationList.tsx`):
- `unread` rows: a 7px `bg-primary` dot at the row end (the same slot as the Running badge; Running wins while
  active), and the title in `font-semibold text-ink`.
- `source === 'schedule'`: a 13px `ClockIcon` before the title, `text-ink-3`, with `title` = "Automation".
- Opening a conversation with `unread` → `PATCH {unread:false}` (optimistic update of the list cache).
- Poll the conversations query every 60 s (`refetchInterval`) so new scheduled chats appear, and fire the
  notification described in step 6 on new unread schedule rows.

## i18n (both files; Arabic needs full plural forms where there's a count)

`nav.automations` Automations / المهام التلقائية · `automations.title` · `automations.subtitle` "Prompts that
run on a schedule and land as new chats" / "طلبات تعمل وفق جدول وتصلك كمحادثات جديدة" · `automations.new` ·
`automations.edit` · `automations.empty` · `automations.examples.*` (3) · `automations.kind.daily|weekdays|weekly|
monthly` · `automations.at` · `automations.every` · `automations.onDays` · `automations.monthlyDay` ·
`automations.lastDayNote` · `automations.timezone` · `automations.next` · `automations.paused` ·
`automations.status.ok|failed|skipped|running` · `automations.runNow` · `automations.enable` ·
`automations.allowedTools` · `automations.pythonWarning` "Runs code on the server without asking you each time."
/ "يشغّل شيفرة على الخادم دون أن يطلب موافقتك في كل مرة." · `automations.deleteConfirm` ·
`automations.limit` · `chat.fromAutomation` "Automation" / "مهمة تلقائية" · `chat.unread` "Unread" / "غير مقروءة".

## Tests
- `test_recurrence.py` (step 4 list).
- `test_chat_runs.py`: the refactor snapshot (step 1).
- `test_unattended.py`: step 2.
- `test_scheduler.py` (`@db`, frozen `now`): a due automation → a conversation created with `source=schedule`,
  `unread=true`, `next_run_at` advanced; a 7-hour-late one → `skipped` and advanced, with no conversation; two
  `_tick()` calls running concurrently start it **once** (two sessions, `asyncio.gather`); `run-now` doesn't
  change `next_run_at`; another user's automation → 404 on every route.
- vitest: `describeRecurrence`, `validateRecurrence`.

## Manual test plan
1. Create "every day at <now + 2 min>" with the prompt "Search today's news on AI in Jordan and write a 1-page
   brief as .docx". Within about 2.5 min a new chat appears with a clock icon and an unread dot, the .docx is
   there, and the card shows Last: ok.
2. Run now works and navigates to the new chat. Pausing stops future runs (the next run shows "Paused").
3. An automation whose prompt forces `run_python` without allowing it: the run finishes, and the trail shows the
   tool declined with the scheduled-run message.
4. Stop the server over a scheduled time for less than 6 h: it runs once on start. Longer than that: skipped.
5. Arabic UI: the recurrence text reads naturally, day chips are in Arabic, and the layout is RTL.
6. Timezone: set `America/New_York` while the browser is in Amman. The "Next" time shown matches New York wall time.

## Rollout
- **PR 1:** step 1 refactor + snapshot test only. Merge and live on it for a day.
- **PR 2:** steps 2–7.

## Done when
- [ ] All tests pass; `scripts/check.sh` is green; manual plan 1–6 passes.
- [ ] README: how the scheduler behaves with several workers (`SCHEDULER_ENABLED=false` on all but one is
      optional; `SKIP LOCKED` already prevents double runs).
