# F5 — Saved prompts with `{{variables}}`

**Size:** M (2–3 days) · **Backend:** yes · **Migration:** yes · **Depends on:** 00-foundation

## What the user gets
- Save any prompt ("Summarize {{file}} for {{audience}} in {{language}}") from a message they sent or from
  scratch.
- Type `/` in an empty composer (or click the **Prompts** pill) to pick one. If it has variables, a small form
  asks for them, and the filled text lands in the composer, ready to edit or send.
- The empty chat shows their four most-used prompts as starter cards.
- Manage them on the Skills page.

## Current state (patterns to copy)
- **CRUD shape:** memories: `db/models.py:UserMemory`, `repositories/memory.py` (limit errors, per-user
  scoping), `schemas/memory.py`, `routes/memory.py`, `api/dependencies.py:MemoryRepositoryDep`,
  `frontend/src/pages/MemoryPage.tsx`. **Copy this structure file for file.**
- Composer toolbar (`components/chat/Composer.tsx`): attach → spacer → `ModelEffortPicker` → send. Pill style is
  in `task.md` §5.7.
- Starters: `STARTERS` in `pages/ChatPage.tsx:~518` (labelKey/promptKey + icon), rendered at ~L872.

## Files

| File | Change |
|---|---|
| `migrations/versions/f6a7b8c9d0e1_saved_prompts.py` | **new** (down_revision = F4's, or `d4e5f6a7b8c9` if F4 isn't merged) |
| `src/agent_console/db/models.py` | `SavedPrompt` + `User.prompts` relationship |
| `src/agent_console/config.py` | `max_saved_prompts=200`, `max_prompt_title_chars=120`, `max_prompt_body_chars=8000` |
| `src/agent_console/repositories/prompts.py` | **new** |
| `src/agent_console/schemas/prompts.py` | **new** |
| `src/agent_console/api/routes/prompts.py` | **new** |
| `src/agent_console/api/dependencies.py` | `PromptRepositoryDep` |
| `src/agent_console/main.py` | `app.include_router(prompts.router)` |
| `frontend/src/lib/promptVars.ts` (+ test) | **new** |
| `frontend/src/hooks/usePrompts.ts` | **new** |
| `frontend/src/lib/api.ts`, `types.ts` | prompts client + `SavedPrompt` type |
| `frontend/src/components/chat/PromptPicker.tsx` | **new**: popover list |
| `frontend/src/components/chat/PromptFillDialog.tsx` | **new**: variables form |
| `frontend/src/components/PromptEditorDialog.tsx` | **new**: create/edit |
| `frontend/src/components/chat/Composer.tsx` | Prompts pill, `/` trigger, `insertText` |
| `frontend/src/pages/ChatPage.tsx` | "Save as prompt" on user turns; starters from prompts |
| `frontend/src/pages/SkillsPage.tsx` | "Prompts" section |
| `frontend/src/components/Icons.tsx` | `BookmarkIcon` |
| `i18n` | keys below |

---

## Step 1: backend

**Model**

```python
class SavedPrompt(Base):
    __tablename__ = "saved_prompts"
    id: Mapped[UUID] = _pk()
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(120))
    body: Mapped[str] = mapped_column(Text)
    use_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = timestamp_column()
    updated_at: Mapped[datetime] = timestamp_column(onupdate=utcnow)
    user: Mapped[User] = relationship(back_populates="prompts")
    __table_args__ = (Index("ix_saved_prompts_user_used", "user_id", "last_used_at"),)
```

Add `prompts: Mapped[list["SavedPrompt"]] = relationship(back_populates="user", cascade="all, delete-orphan")`
to `User`. The migration mirrors `d4e5f6a7b8c9_user_skills.py` exactly (columns, FK with CASCADE, index, and a
downgrade that drops the index then the table).

**Repository** (`repositories/prompts.py`), mirroring `MemoryRepository`:

```python
class UnknownPromptError(LookupError): ...
class PromptLimitError(ValueError): ...

class PromptRepository:
    def __init__(self, session, *, max_items=200, max_title=120, max_body=8000): ...
    async def list_for(self, user_id) -> list[SavedPrompt]:
        # most recently used first, never-used after them by newest created
        order_by(SavedPrompt.last_used_at.desc().nulls_last(), SavedPrompt.created_at.desc())
    async def get(self, user_id, prompt_id) -> SavedPrompt           # UnknownPromptError if not theirs
    async def create(self, user_id, title, body) -> SavedPrompt      # count check → PromptLimitError
    async def update(self, user_id, prompt_id, title=None, body=None) -> SavedPrompt
    async def delete(self, user_id, prompt_id) -> None
    async def mark_used(self, user_id, prompt_id) -> SavedPrompt     # use_count += 1, last_used_at = utcnow()
```

`_validate(title, body)`: strip both. Empty after stripping → `PromptLimitError("title and text are required")`.
Too long → `PromptLimitError` naming the limit.

**Schemas:** `PromptCreateRequest(title: str, body: str)`, `PromptUpdateRequest(title: str | None, body: str |
None)`, `PromptResponse(id, title, body, use_count, last_used_at, created_at, updated_at)` with
`from_attributes`, and `PromptListResponse(prompts: list[PromptResponse])`.

**Routes** (`/api/prompts`), same error mapping as memory (Unknown → 404, Limit → 400):
`GET ""`, `POST ""` (201), `PATCH "/{id}"`, `DELETE "/{id}"` (204), `POST "/{id}/used"` → `PromptResponse`.

## Step 2: `lib/promptVars.ts`

```ts
// {{ name }} with optional spaces; names may be Arabic, digits, _, -, space (1–40 chars).
const VAR = /\{\{\s*([\p{L}\p{N}_\- ]{1,40}?)\s*\}\}/gu

/** Unique variable names in order of first appearance. */
export function extractVars(body: string): string[] {
  const seen = new Set<string>()
  for (const match of body.matchAll(VAR)) seen.add(match[1].trim())
  return [...seen]
}

/** Replace each {{name}} with its value; unknown or empty values leave the placeholder. */
export function fillVars(body: string, values: Record<string, string>): string {
  return body.replace(VAR, (whole, raw: string) => {
    const value = values[raw.trim()]
    return value && value.trim() ? value : whole
  })
}
```

Tests: order and uniqueness (`{{a}} {{b}} {{a}}` → `[a, b]`), spaces (`{{ audience }}`), Arabic
(`{{الجمهور}}`), unbalanced (`{{a}` and `{a}}` ignored), a name longer than 40 ignored, fill with a missing value
keeps `{{x}}`, and fill replaces every occurrence.

## Step 3: data hooks
`hooks/usePrompts.ts` with react-query, like `useConversations.ts`:
- `usePrompts()` → the list (`queryKey: ['prompts']`, `staleTime: 30_000`);
- `useCreatePrompt`, `useUpdatePrompt`, `useDeletePrompt` (invalidate `['prompts']`);
- `useMarkPromptUsed()`: optimistic, bumps `use_count`/`last_used_at` in the cache, fire-and-forget.

## Step 4: `PromptPicker` (popover)
- Anchored above the composer (`bottom-full mb-2 start-0`), `w-[min(100%,26rem)]`, `rounded-[14px] border
  border-line bg-surface shadow-md`, `max-h-[360px]` with a scrolling list.
- A search field at the top (autofocus) filters title + body, case-insensitive, and also with
  `normalize` for Arabic (port the step-4 normalization from F4 into `lib/textNormalize.ts` if F4 exists,
  otherwise do a simple lowercase).
- Rows: title (13px semibold, `dir="auto"`, truncate), first line of the body (12px `text-ink-3`, truncate), and
  a small `{{n}}` chip if it has variables.
- Keyboard: Up/Down moves the active row (`aria-activedescendant` on the input), Enter picks, Esc closes and
  returns focus to the composer. `role="listbox"` and `role="option"`.
- The footer has a "New prompt" button (opens `PromptEditorDialog`) and a "Manage" link to `/skills#prompts`.
- Empty state: `prompts.empty` + "New prompt".

## Step 5: `PromptFillDialog`
- Uses the same dialog shell as `ConfirmDialog.tsx` (focus trap, Esc, scrim).
- The title is the prompt title. One `.field` per variable, labelled with the variable name, `dir="auto"`, the
  first field autofocused. Enter in the last field submits.
- A live preview underneath (`fillVars(body, values)` in a `text-ink-2 text-[13px]` box, `whitespace-pre-wrap`).
- The **Insert** button (primary) calls `onInsert(filled)`. Empty fields are allowed and keep their placeholder,
  so the user can finish in the composer.

## Step 6: Composer integration
`Composer.tsx`:
1. **Pill:** after the attach button, a `Prompts` pill (`BookmarkIcon` 14px + label, pill style from §5.7) that
   toggles `PromptPicker`.
2. **`/` trigger:** in the textarea `onKeyDown`, if `event.key === '/'` and the textarea value is empty
   (after trim) and there's no IME composition (`!event.nativeEvent.isComposing`), call `preventDefault()` and
   open the picker. Typing `/` anywhere else types a normal slash.
3. **Insert:** `insertText(text)` replaces an empty composer, or inserts at the cursor (use
   `setRangeText(text, start, end, 'end')` on the textarea), then focuses and resizes it (reuse the existing
   auto-grow logic) and calls `markUsed(id)`.
4. Pick flow: `extractVars(body).length === 0` → insert directly; otherwise open `PromptFillDialog` → insert.

## Step 7: "Save as prompt" and management
- **User turns** (`ChatPage.tsx`, where the hover edit button renders): add a `BookmarkIcon` button
  (`prompts.save`) that opens `PromptEditorDialog` prefilled with `body = turn.text` stripped of the attachments
  note (remove the trailing `t('chat.attachedFiles', …)` line if present) and `title` = the first 60 chars.
- **`PromptEditorDialog`:** title `.field`, body `textarea.field` (min 6 rows, `dir="auto"`), and a hint
  `prompts.bodyHint` with the detected variables shown as chips under it (live, from `extractVars`). Save
  and Cancel. Server 400 messages are shown inline.
- **Skills page:** a `<section id="prompts">` below skills: a header with "New prompt", then cards (`.card`)
  showing title, body excerpt (3 lines, `line-clamp-3`), "Used N times", and edit/delete icon buttons (delete
  uses `ConfirmDialog`).

## Step 8: starters from prompts
In the empty-chat branch of `ChatPage.tsx`: `const { data: prompts = [] } = usePrompts()`. If
`prompts.length > 0`, render the top 4 by `use_count` (then newest) as starter cards in the same grid, with
`BookmarkIcon`. Clicking one runs the same pick flow as the composer (fill dialog if it has variables), then
**inserts** instead of sending, because a saved prompt usually needs editing. If there are no prompts, keep the
current `STARTERS`.

## i18n

| key | en | ar |
|---|---|---|
| `prompts.title` | Prompts | القوالب |
| `prompts.new` | New prompt | قالب جديد |
| `prompts.edit` | Edit prompt | تعديل القالب |
| `prompts.save` | Save as prompt | حفظ كقالب |
| `prompts.search` | Search prompts | ابحث في القوالب |
| `prompts.manage` | Manage | إدارة |
| `prompts.empty` | No saved prompts yet | لا توجد قوالب محفوظة بعد |
| `prompts.fill` | Fill in the details | أكمل التفاصيل |
| `prompts.insert` | Insert | إدراج |
| `prompts.titleLabel` | Title | العنوان |
| `prompts.bodyLabel` | Prompt | نص القالب |
| `prompts.bodyHint` | Use {{name}} for parts you fill in each time | استخدم {{name}} للأجزاء التي تملؤها في كل مرة |
| `prompts.variables` | Variables | المتغيرات |
| `prompts.usedCount_one`/`_other` | Used {{count}} time / times | (ar: six plural forms) |
| `prompts.deleteConfirm` | Delete this prompt? | حذف هذا القالب؟ |

**i18next interpolation clash:** `{{name}}` inside `prompts.bodyHint` would be interpolated by i18next. Write
the value as `Use {{varExample}} for…`, pass `{ varExample: '{{name}}' }` at the call site, and set
`interpolation: { escapeValue: false }` for that call only if it isn't already global. Check this renders
literally in both languages.

## Tests
- vitest `promptVars` (step 2 list).
- pytest `@db`: user B gets 404 on user A's prompt for GET/PATCH/DELETE/used; the 201st create → 400; an empty
  title → 400; `mark_used` increments and orders the list.

## Manual test plan
1. Save "Summarize {{file}} for {{audience}}" from a sent message, then type `/` in a new chat, pick it, fill
   both fields, and insert: the composer holds the filled text.
2. `/` in the middle of text types a slash. `/` during Arabic IME composition doesn't open the picker.
3. The empty chat shows the saved prompts as starters, and clicking one fills and inserts.
4. Skills page: edit and delete work. Arabic titles are RTL. Keyboard-only flow works end to end.

## Done when
- [ ] Tests pass; `scripts/check.sh` is green; manual plan 1–4 passes in EN/AR, light/dark.
