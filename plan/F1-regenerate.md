# F1 — Regenerate answer

**Size:** S (½–1 day) · **Backend:** none · **Migration:** none · **Depends on:** 00-foundation

## What the user gets
Under the **latest** assistant answer, next to Copy, there's a **Regenerate** button. It deletes the last
answer and runs the same question again. A chevron beside it opens **"Try again with…"**, listing effort levels
and loaded models, to retry once with a different setting without changing the composer's saved choice.

## How it works (and why no backend change)
Edit-and-resend already does exactly this sequence (`frontend/src/hooks/useChat.ts:125`):

1. `stopChatRun(conversationId)`
2. `api.conversations.rewind(conversationId, turnIndex)` → `POST /api/conversations/{id}/rewind {keep}`
   → `ConversationRepository.truncate_from` deletes messages from position `keep` on.
3. `startChatRun({... message, priorTurns: turns.slice(0, turnIndex), model, effort })` → `POST /api/chat`.

`ChatRequest` (`src/agent_console/schemas/chat.py`) already takes `model` and `effort` per request.
Regenerate = the same sequence with `turnIndex` = the **last user turn**, `text` = that turn's text, and
optional model/effort overrides.

Attachments are safe: they're embedded in the user message text by `withAttachments()` in `ChatPage.tsx:651`
(`t('chat.attachedFiles', {names})`), so resending the same text resends the references.

**Known limit (accepted for v1):** the per-turn composer toggles (web search / research / skill) aren't stored
on `Turn`, so a regenerated turn runs without them. Say so in a code comment. Storing them is a later change.

## Files

| File | Change |
|---|---|
| `frontend/src/lib/turns.ts` | **new**: `lastUserTurnIndex()` |
| `frontend/src/lib/turns.test.ts` | **new**: tests |
| `frontend/src/hooks/useModels.ts` | **new**: shared `/api/models` query |
| `frontend/src/hooks/useChat.ts` | add `rerunFrom` + `regenerate`; `editAndResend` delegates |
| `frontend/src/components/chat/ModelEffortPicker.tsx` | use `useModels()`; export `EFFORTS`, `effortLabelKey` |
| `frontend/src/components/chat/RegenerateButton.tsx` | **new** |
| `frontend/src/components/Icons.tsx` | add `RefreshIcon` |
| `frontend/src/pages/ChatPage.tsx` | render the button in the turn-actions row |
| `frontend/src/i18n/en.json`, `ar.json` | 4 keys |

## Step 1: `lib/turns.ts`

```ts
import type { Turn } from '@/types'

/** Index of the last user turn, or -1. The answer to regenerate follows it. */
export function lastUserTurnIndex(turns: Turn[]): number {
  for (let index = turns.length - 1; index >= 0; index -= 1) {
    if (turns[index].role === 'user') return index
  }
  return -1
}
```

`lib/turns.test.ts`:

```ts
import { describe, expect, it } from 'vitest'
import { lastUserTurnIndex } from './turns'

describe('lastUserTurnIndex', () => {
  it('finds the user turn before the last answer', () => {
    expect(lastUserTurnIndex([
      { role: 'user', text: 'a' }, { role: 'assistant', blocks: [] },
      { role: 'user', text: 'b' }, { role: 'assistant', blocks: [] },
    ])).toBe(2)
  })
  it('handles a trailing user turn (failed run)', () => {
    expect(lastUserTurnIndex([{ role: 'user', text: 'a' }])).toBe(0)
  })
  it('returns -1 for an empty chat', () => {
    expect(lastUserTurnIndex([])).toBe(-1)
  })
})
```

## Step 2: `hooks/useModels.ts`

Move the query out of `ModelEffortPicker.tsx` (L50–56) so both components share one cache entry:

```ts
import { useQuery } from '@tanstack/react-query'
import { api } from '@/lib/api'

export function useModels() {
  const { data } = useQuery({ queryKey: ['models'], queryFn: api.models, staleTime: 60_000 })
  return { models: data?.models ?? [], current: data?.current ?? null }
}
```

In `ModelEffortPicker.tsx`, replace the `useQuery` block with `const { models, current } = useModels()` and use
`current` where it read `data?.current`. Also `export` `EFFORTS` and `effortLabelKey` (they're module-private today).

## Step 3: `useChat.ts`: `rerunFrom` and `regenerate`

Replace the body of `editAndResend` with a shared internal function. Keep `editAndResend`'s public signature
unchanged (ChatPage calls it at L646).

```ts
type RerunOptions = {
  model?: string
  effort?: Effort
  webSearch?: boolean
  research?: boolean
  skill?: string | null
}

const rerunFrom = useCallback(
  async (turnIndex: number, text: string, options: RerunOptions = {}) => {
    const trimmed = text.trim()
    if (!trimmed || !conversationId || busy) return
    const turn = turns[turnIndex]
    if (!turn || turn.role !== 'user') return

    stopChatRun(conversationId)
    await api.conversations.rewind(conversationId, turnIndex)
    const prior = turns.slice(0, turnIndex)
    setLocalTurns(prior)
    void queryClient.invalidateQueries({ queryKey: conversationKeys.detail(conversationId) })
    startChatRun({
      conversationId,
      message: trimmed,
      priorTurns: prior,
      model: options.model ?? model,
      effort: options.effort ?? effort,
      title,
      webSearch: options.webSearch,
      research: options.research,
      skill: options.skill,
    })
  },
  [conversationId, turns, busy, model, effort, title, queryClient],
)

const editAndResend = useCallback(
  (turnIndex: number, text: string,
   options?: { webSearch?: boolean; research?: boolean; skill?: string | null }) =>
    rerunFrom(turnIndex, text, options),
  [rerunFrom],
)

/**
 * Drop the last answer and ask the same question again, optionally once with
 * another model/effort. Composer toggles (web/research/skill) are not stored
 * per turn, so a regenerated turn runs without them.
 */
const regenerate = useCallback(
  (overrides?: { model?: string; effort?: Effort }) => {
    const index = lastUserTurnIndex(turns)
    if (index < 0) return
    const turn = turns[index]
    if (turn.role !== 'user') return
    return rerunFrom(index, turn.text, overrides)
  },
  [turns, rerunFrom],
)
```

Return `regenerate` from the hook.

## Step 4: `RefreshIcon` in `Icons.tsx`

Same shape as the other icons (24×24, stroke 1.75, round caps/joins):

```tsx
export const RefreshIcon: Icon = (props) => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.75}
    strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" {...props}>
    <path d="M20 11a8 8 0 1 0-2.3 5.7" />
    <path d="M20 4v7h-7" />
  </svg>
)
```

## Step 5: `components/chat/RegenerateButton.tsx`

- Two adjacent buttons in one group: the main icon button (32×32, the same classes as `TurnCopyButton`:
  `text-ink-3 hover:bg-paper-3 hover:text-ink rounded-lg`) and a narrow chevron button (20×32) that opens
  a menu.
- The menu reuses the open/close pattern of `ModelEffortPicker` (outside-click + Escape closes it, focus
  returns to the chevron). It opens **upward** (`bottom-full mb-1`), anchored `start-0`.
- Menu content:
  1. Section label `chat.regenerateWith`.
  2. The four efforts from `EFFORTS` with `t(effortLabelKey(level))`. A check mark on the current one, and
     clicking the current one still runs.
  3. A divider, then models from `useModels()` (only if more than one), with the current one marked.
- Picking an item closes the menu and calls `onRegenerate({ effort })` or `onRegenerate({ model })`.

```tsx
interface Props {
  model: string | null
  effort: Effort
  onRegenerate: (overrides?: { model?: string; effort?: Effort }) => void
}
```

Menu items are `role="menuitemradio"` with `aria-checked`, and the menu is `role="menu"`. Arrow Up/Down moves
focus between items, and Home/End jump to the first/last.

## Step 6: `ChatPage.tsx`

1. Destructure `regenerate` from `useChat(...)` (next to `editAndResend`, ~L538).
2. In the turn-actions row (~L957, where `TurnCopyButton` renders), after the copy button:

```tsx
{index === turns.length - 1 && turn.role === 'assistant' ? (
  <RegenerateButton
    model={model}
    effort={effort}
    onRegenerate={(overrides) => void regenerate(overrides)}
  />
) : null}
```

The surrounding `!(busy && index === turns.length - 1)` guard already hides the row while busy. Keep it.

## Step 7: i18n

| key | en | ar |
|---|---|---|
| `chat.regenerate` | Regenerate | إعادة التوليد |
| `chat.regenerateWith` | Try again with… | أعد المحاولة باستخدام… |
| `chat.regenerateMenu` | Regenerate options | خيارات إعادة التوليد |
| `chat.regenerateModels` | Model | النموذج |

## Test plan (manual, in the running app)
1. Ask a question, wait for the answer, then press Regenerate. The old answer disappears, a new one streams in,
   and after a page reload only the new answer is stored.
2. Open the chevron and pick "Thorough". In DevTools → Network, the `/api/chat` payload has `"effort":"xhigh"`.
   The composer picker still shows the old effort.
3. Older assistant turns have no Regenerate button. While running, there's no button at all.
4. With an attachment on the last user turn: after Regenerate, the agent still refers to the file.
5. Arabic UI: the menu opens toward the correct side, and labels are translated.
6. Keyboard: Tab reaches both buttons, Enter opens the menu, arrows move through it, and Esc closes it.

## Done when
- [ ] `lastUserTurnIndex` tests pass; `npm run build && npm run lint` has no new warnings.
- [ ] Manual test plan 1–6 passes.
