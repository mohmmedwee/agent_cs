# Task: "Quiet Workbench" redesign of the cleverso-ai frontend

You are implementing a visual and layout redesign of the React frontend in `frontend/`.
Read this whole file before changing anything. Do exactly what it says; where it is silent,
match the existing code style.

## 0. Ground rules

- **Frontend only.** Do not touch `src/`, `migrations/`, `skills/`, or any backend file. No API changes.
- **The working tree has uncommitted changes.** Do not revert, stash, reset or reformat files you are not asked to change.
- **Keep behavior identical.** Streaming, background runs, approvals, queueing, branching, edit-and-resend,
  drag-and-drop upload, the artifact preview (docx/xlsx/image/text), context compaction, i18n and theme
  switching must all work as they do now. This is a restyle and re-layout, not a rewrite of logic.
- **Bilingual + RTL is mandatory.** Every new visible string goes in BOTH `frontend/src/i18n/en.json` and
  `frontend/src/i18n/ar.json`. Use logical properties only (`ps-`, `pe-`, `ms-`, `me-`, `start-`, `end-`,
  `border-s`, `border-e`, `text-start`). Never `pl-`/`pr-`/`ml-`/`mr-`/`left-`/`right-` for layout.
  Directional icons (chevrons, send arrow) keep `rtl:-scale-x-100` where they have it now.
- **Dark mode is mandatory.** Every new token gets a dark value in the `.dark` block of `styles.css`.
- Keep Tailwind v4 + the existing `@theme` approach. No new dependencies. No CSS-in-JS.
- Icons: reuse `frontend/src/components/Icons.tsx`. If an icon is missing, add it there in the same style
  (24×24 viewBox, `stroke="currentColor"`, stroke-width 1.75, round caps/joins). No emoji anywhere in the UI.
- Accessibility: real `<button>`/`<a>`; `aria-label` on every icon-only button; visible `:focus-visible`
  outline (already in `styles.css`, keep it); hit targets at least 36×36px (44×44 in the nav rail);
  body text at least 4.5:1 contrast in both themes.
- After each phase run `cd frontend && npm run build && npm run lint`. Both must pass before the next phase.

## 1. Design direction (what "done" looks like)

"Quiet Workbench": warm paper-toned neutrals instead of cold grey, the brand violet `#673CDB` used
**sparingly** (primary action, send, active/selected accents only), content first, chrome quiet.

Layout on desktop (≥1024px), three zones:

```
┌──────┬──────────────┬───────────────────────────────┬──────────────────────┐
│ Rail │ Conversations│ Conversation (header, thread, │ Workspace (optional) │
│ 68px │ 260px        │ composer), flexible width     │ 460px, only when a   │
│ dark │ paper ground │ slightly lighter paper ground │ file is open         │
└──────┴──────────────┴───────────────────────────────┴──────────────────────┘
```

- **Rail** (dark ink): New chat button on top, then nav icons (Chat, Files, Memory, Skills), spacer,
  Admin (admins only), Settings, avatar/profile button at the bottom.
- **Conversations panel**: logo + language toggle, search field, conversation list grouped by date.
  Only shown on the Chat routes (`/chat`, `/chat/:id`). On Files/Memory/Skills/Settings/Admin the page
  content sits directly beside the rail.
- **Conversation column**: a 60px header with the conversation title, the thread (max width 720px when the
  workspace is closed, 600px when it is open), and the composer pinned to the bottom.
- **Workspace**: the current `ArtifactPanel`, restyled, with tabs (see section 5.6).

## 2. Design tokens (`frontend/src/styles.css`)

The existing brand tokens were copied from the Cleverso portal design system; **do not change their
values** (`--color-primary*`, `--color-error*`, `--color-success*`, `--color-warning*`, `--color-info`).
Add the new tokens below to the `@theme` block, and dark values to the `.dark` block.

| Token | Light | Dark | Use |
|---|---|---|---|
| `--color-paper` | `#F6F5F1` | `#141317` | app ground, conversations panel |
| `--color-paper-2` | `#FBFAF7` | `#18171C` | conversation column ground |
| `--color-paper-3` | `#EFEDE7` | `#232129` | user bubble, search field, selected tab, chips |
| `--color-paper-4` | `#F3F1EC` | `#1E1D23` | workspace preview backdrop |
| `--color-line` | `#E7E4DD` | `#2E2C35` | borders |
| `--color-line-soft` | `#EFEDE7` | `#25232B` | header dividers |
| `--color-ink` | `#1C1A24` | `#F2F1F5` | primary text |
| `--color-ink-2` | `#55525F` | `#B9B5C4` | secondary text, icon buttons |
| `--color-ink-3` | `#6E6A78` | `#8F8B9B` | captions, section labels (check 4.5:1) |
| `--color-rail` | `#19171F` | `#0E0D11` | nav rail background |
| `--color-rail-active` | `#2E2B38` | `#26232F` | active rail item |
| `--color-rail-icon` | `#A9A5B4` | `#8F8B9B` | inactive rail icons |
| `--color-violet-tint` | `#F1ECFD` | `#241A3A` | active chip bg, focus ring halo |
| `--color-violet-line` | `#D9CCF8` | `#3A2A5C` | active chip border |
| `--color-violet-ink` | `#4F2BB0` | `#BB91FF` | text on violet tint |

Also:
- `body` background → `var(--color-paper)`.
- Change `.btn-primary` to a **flat** `background: var(--color-primary)`; hover `var(--color-primary-600)`.
  Remove the gradient.
- `.card` → `rounded-2xl border border-line bg-surface` (keep the shadow-sm).
- `.field` → border `border-line`, background `bg-surface`, focus `border-primary-300` plus
  `box-shadow: 0 0 0 4px var(--color-violet-tint)`.
- Add a mono font token `--font-mono: "IBM Plex Mono", ui-monospace, "SF Mono", Menlo, monospace;` and load
  IBM Plex Mono 400/500 the same way Noto Kufi Arabic is loaded (self-host under `src/assets/fonts/` if
  the Kufi font is self-hosted; do not add a Google Fonts link if everything else is local).
  Mono is used ONLY for durations, keyboard hints and token counts.
- Keep `Noto Kufi Arabic` as `--font-sans`.

Radii: controls 10–12px, cards 14px, composer 20px, pills 999px. Shadows: composer
`0 8px 24px -12px rgb(28 26 36 / 0.18)`; everything else flat or `shadow-sm`.

## 3. New files to create

1. `frontend/src/components/NavRail.tsx`: the dark rail (section 5.1).
2. `frontend/src/components/ConversationList.tsx`: the conversations panel (section 5.2), extracted from `Sidebar.tsx`.
3. `frontend/src/lib/groupConversations.ts`: pure function
   `groupConversations(list: ConversationSummary[], now = new Date()): { key: 'today'|'yesterday'|'week'|'older'; items: ConversationSummary[] }[]`
   grouping by `updated_at` (local time): Today, Yesterday, Previous 7 days, Older. Drop empty groups,
   keep input order within groups (API order is already newest first; do not re-sort).

Then **delete** `frontend/src/components/Sidebar.tsx` once nothing imports it.

## 4. i18n keys to add (both `en.json` and `ar.json`)

```
nav.searchChats        "Search chats"            / "ابحث في المحادثات"
nav.groupToday         "Today"                   / "اليوم"
nav.groupYesterday     "Yesterday"               / "أمس"
nav.groupWeek          "Previous 7 days"         / "آخر 7 أيام"
nav.groupOlder         "Older"                   / "أقدم"
nav.running            "Running"                 / "قيد التشغيل"
nav.noResults          "No chats match"          / "لا توجد محادثات مطابقة"
chat.greeting          "What should we work on?" / "على ماذا نعمل اليوم؟"
chat.replyPlaceholder  "Reply to cleverso-ai…"   / "رد على cleverso-ai…"
chat.stepsSummary      "{{count}} steps"         / "{{count}} خطوات"
workspace.preview      "Preview"                 / "معاينة"
workspace.files        "Files"                   / "الملفات"
workspace.sources      "Sources"                 / "المصادر"
workspace.steps        "Steps"                   / "الخطوات"
workspace.close        "Close workspace"         / "إغلاق مساحة العمل"
workspace.fullscreen   "Open full screen"        / "ملء الشاشة"
```

Reuse existing keys wherever one already exists (e.g. `nav.newChat`, `chat.placeholder`, `chat.disclaimer`,
starter keys). Do not rename or delete existing keys.

## 5. Component-by-component changes

### 5.1 `NavRail.tsx` (new) + `AppShell.tsx`

- `NavRail`: `<nav aria-label={t('nav.main')}>`, width 68px, `bg-rail`, full height, vertical flex,
  `items-center`, `py-4`, `gap-1.5`. Add `nav.main` = "Main" / "الرئيسية" to i18n.
- Top: New chat button, 44×44, `rounded-[14px] bg-primary text-white`, `PlusIcon` 18px,
  `aria-label={t('nav.newChat')}`, `mb-3.5`. Same `startChat` logic that is in `Sidebar.tsx` today.
- Nav items (`NavLink`, 44×44, `rounded-xl`, centered icon 18px, `aria-label` + `title` = label):
  Chat, Files, Memory, Skills. Active: `bg-rail-active text-white`. Inactive:
  `text-rail-icon hover:text-white hover:bg-rail-active/60`. For Chat, treat any `/chat*` path as active.
- Spacer `flex-1`, then Admin (only if `user?.is_admin`), Settings, then `ProfileMenu` restyled as a 36px
  round avatar button with the user's initials (`bg-violet-tint text-violet-ink text-xs font-bold`).
  The ProfileMenu popover must open towards the inline-end side of the rail, not off-screen, in both LTR and RTL.
- `AppShell`: `flex h-dvh bg-paper` → `<NavRail/>`, then `{isChatRoute && <ConversationList/>}`, then
  `<main>` with `<Outlet/>`. `isChatRoute` = pathname starts with `/chat`.
- Remove the old collapse toggle; the `sidebar-collapsed` local setting now controls only the
  conversations panel (see 5.2).

### 5.2 `ConversationList.tsx` (new)

- `<aside aria-label={t('nav.conversations')}>`, width 260px, `bg-paper border-e border-line`,
  `px-3.5 pt-5 pb-3.5`, vertical flex.
- Header row: `<Logo className="h-6" />` at the start, `<LanguageToggle compact />` at the end, restyled as a
  30px-high pill (`rounded-full border border-line bg-surface text-xs font-semibold text-ink-2 px-2.5`).
- Search: a `<label>` wrapping `SearchIcon` 15px + `<input type="search">`, height 40px,
  `rounded-xl bg-paper-3 px-3 text-[13px]`, placeholder `t('nav.searchChats')`, plus a `⌘K` hint in mono
  11px `text-ink-3` at the end (hide the hint on touch devices, hide it when the input has text).
  Filtering is client-side, case-insensitive, on `title`. `Cmd/Ctrl+K` focuses it (register the listener in
  this component; ignore it while typing in another input or textarea).
  Empty result shows `t('nav.noResults')` in `text-ink-3 text-xs px-2.5`.
- List: groups from `groupConversations`. Group label: `px-2.5 pb-1.5 text-[11px] font-semibold uppercase
  tracking-[0.06em] text-ink-3` (in Arabic: no uppercase, no letter-spacing, use `rtl:normal-case rtl:tracking-normal`).
  Gap between groups 18px (`space-y-[18px]`), list scrolls (`overflow-y-auto`, `min-h-0 flex-1`).
- Row (`NavLink`): height 36px, `rounded-[10px] px-2.5 text-[13px]`, title truncated, `dir="auto"` on the title.
  Inactive: `text-[#3D3A47] dark:text-ink-2 hover:bg-paper-3`. Active: `bg-surface text-ink font-semibold`
  with `shadow-[0_1px_2px_rgb(28_26_36/0.08),0_0_0_1px_var(--color-line)]`.
- Running indicator: if `isChatBusy(conversation.id)` from `@/lib/chatRunner` is true, show at the row end a
  7px `bg-primary` dot with a 3px `violet-tint` ring plus the text `t('nav.running')` (11px,
  `text-violet-ink font-semibold`). Subscribe to changes with `subscribeChatRun` (look at its signature in
  `lib/chatRunner.ts`) so the dot appears and disappears live. The dot pulses (`animate-pulse`) but respects
  `motion-reduce:animate-none`.
- Delete button: keep the existing hover-revealed trash button and `ConfirmDialog` flow exactly as in
  `Sidebar.tsx`; when the row is running, the running badge hides on hover and the trash shows instead.
- Collapsing: a small icon button at the end of the header row (`aria-label` `nav.collapse`) hides the panel
  (store in `useLocalSetting('sidebar-collapsed')`). When collapsed, the conversation header (5.3) shows an
  "expand" icon button at its start (`aria-label` `nav.expand`).

### 5.3 Conversation header (`ChatPage.tsx` + `ChatSessionBar.tsx`)

- A 60px header row at the top of the conversation column: `h-[60px] px-6 flex items-center gap-3
  border-b border-line-soft bg-paper-2`.
- Start: the conversation title as a button (15px, semibold, `text-ink`, chevron-down 15px) that opens the
  existing rename behavior if there is one (use `useRenameConversation`); if there is no rename UI today,
  make it an inline rename (click → input, Enter saves, Esc cancels).
- If the conversation is a branch (`parent_id` set), a pill after the title: `h-[26px] px-2.5 rounded-full
  bg-paper-3 text-ink-2 text-xs` with a branch icon (add `BranchIcon` to `Icons.tsx`: circles at (6,5),
  (6,19), (18,8) r=2, path `M6 7v10M18 10c0 4-6 3-11.5 7`).
- End: move the current `ChatSessionBar` content here (status chip + context meter), restyled with the new
  tokens, then a `More` icon button if one exists today. Do not change the session bar's logic.

### 5.4 Thread (`ChatPage.tsx`, `Blocks.tsx`, `styles.css`)

- Column: `mx-auto w-full max-w-[720px]` (use `max-w-[600px]` while the workspace is open), `pt-8`,
  gap between turns `28px`.
- **User turn**: aligned to the inline-end. Bubble `max-w-[460px] rounded-[18px] rounded-ee-[6px]
  bg-paper-3 px-4 py-3 text-[14.5px] leading-relaxed text-ink`, `dir="auto"`. Attached files render ABOVE
  the bubble as file chips: `rounded-xl border border-line bg-surface p-2 pe-3`, a 32px type badge
  (see 5.5 badge colors), file name 13px semibold and a 11px `text-ink-3` subline. Keep the existing edit
  button, revealed on hover/focus below the bubble.
- **Assistant turn**: no bubble, no avatar. Order stays as today (answer text → file cards → activity),
  BUT the activity summary moves ABOVE the answer and becomes a single pill (next bullet).
- **Activity pill** (restyle `TurnActivity` in `ChatPage.tsx`, keep its open/closed logic):
  collapsed state = `inline-flex items-center gap-2.5 rounded-full border border-line bg-surface
  py-1.5 ps-1.5 pe-3 text-xs text-ink-2`.
  - Leading 22px circle: done = `bg-success-50 text-success` with `CheckIcon`; busy = `bg-violet-tint
    text-primary` with `SpinnerIcon`; error = `bg-error-50 text-error`.
  - Then up to three step labels, each with its 15px icon (file → `FileIcon`, web search/fetch →
    `GlobeIcon`, write/convert → `EditIcon`, python → a new `CodeIcon` `M9 8l-4 4 4 4M15 8l4 4-4 4`,
    skill → `SparkIcon`, reasoning → `BrainIcon`), separated by a `·` in `text-line`.
    More than three: show the first two, then `t('chat.stepsSummary', {count})`.
  - Then the total duration if it is available from block timing (mono 11px `text-ink-3`); if timing is not
    stored today, omit it. Do not add backend fields.
  - Trailing chevron-down 15px, rotated 180° when open.
  - Expanded state: the pill stays, and the step list renders below it inside
    `mt-2 rounded-2xl border border-line bg-surface p-3 space-y-2`, using the existing `BlockView`.
  - While streaming, the pill shows the live label (current behavior) with the spinner.
- **Answer prose** (`.chat-answer`, `.prose-agent`): `text-[14.5px] leading-[1.7] text-ink`; `h3` 15px
  semibold, normal case, normal tracking, `text-ink`, `mt-1.5`; list items gap 6px; links `text-violet-ink
  underline underline-offset-2`; inline code `bg-paper-3`; `pre` stays dark. Tables: header `bg-paper-3`,
  borders `border-line`. Keep `.prose-agent--compact` but map its colors to `text-ink-2`.
- **Turn actions** (copy, retry, branch; whatever exists today): a row of 32×32 icon buttons,
  `text-ink-3 hover:bg-paper-3 hover:text-ink rounded-lg`, visible on hover/focus of the turn and ALWAYS
  visible on the latest assistant turn.

### 5.5 File card (`DocumentPreview.tsx` → `DocumentFileCard`)

- `flex items-center gap-3.5 rounded-[14px] border border-line bg-surface px-3.5 py-3`.
- When this file is the one open in the workspace: `border-[1.5px] border-primary
  shadow-[0_0_0_4px_var(--color-violet-tint)]`.
- 40px type badge, `rounded-[10px]`, text 11px bold, by extension:
  DOCX `bg-[#E8F0FE] text-[#1D4ED8]`, XLSX/CSV `bg-[#E6F4EA] text-[#1E7B34]`, PDF `bg-[#FDECEC] text-[#B42318]`,
  image `bg-violet-tint text-violet-ink`, anything else `bg-paper-3 text-ink-2`. Add dark-mode variants
  with the same hue at low lightness (e.g. DOCX `dark:bg-[#172554] dark:text-[#93C5FD]`).
  Put this in ONE helper `fileBadgeClass(name)` in `DocumentPreview.tsx` and reuse it in the user-turn
  attachment chips, the workspace header and the Files page.
- Middle: name 14px semibold (`dir="auto"`, truncate), subline 12px `text-ink-3` (type · "open in workspace").
- End: download icon button 36×36 `rounded-[10px] border border-line text-ink-2`.
- Clicking the card body opens it in the workspace (existing behavior).

### 5.6 Workspace (`DocumentPreview.tsx` → `ArtifactPanel`)

- Width 460px at `lg`, full-screen overlay below `md` (keep the current responsive behavior, only restyle).
  `bg-surface border-s border-line`.
- Header 60px: a tablist on the start (`role="tablist"`), buttons `h-8 px-3 rounded-lg text-[13px]`;
  selected `bg-paper-3 text-ink font-semibold`, others `text-ink-2`. Tabs:
  - **Preview**: the current preview behavior, unchanged.
  - **Files**: all files produced in this conversation (derive from the turns' written-file blocks the same
    way `AssistantTurnBlocks` does; lift that derivation into a shared helper rather than duplicating it).
    Clicking one switches Preview to it.
  - **Sources**: all web search hits / fetched URLs in this conversation (reuse `parseSearchResultText` from
    `WebSearchResults.tsx`), as a list of title + domain links. Hide the tab when there are none.
  - **Steps**: the full activity trail of the turn that produced the open file (reuse `BlockView`).
  Counts next to Files/Sources in `text-ink-3`. Keep the current expand and close buttons at the end,
  as 34px icon buttons with the new aria-labels.
- Sub-header row: badge (28px) + file name 13px semibold + primary `Download` button (`h-8 px-3
  rounded-[10px] bg-primary text-white text-xs font-semibold` with `DownloadIcon`).
- Body: `bg-paper-4 p-6`; the docx/xlsx/text preview sits on a white "sheet":
  `bg-white rounded shadow-[0_1px_2px_rgb(28_26_36/0.06),0_8px_24px_-16px_rgb(28_26_36/0.25)]`.
  The sheet stays white in dark mode (it's a document), the backdrop goes dark.
- Wire the workspace-open state into the thread width (5.4) through `useArtifact()`.

### 5.7 Composer (`Composer.tsx`, `ModelEffortPicker.tsx`)

- Container: `mx-auto w-full max-w-[720px]` (600 when workspace open), `rounded-[20px] border
  border-[#E0DCD3] dark:border-line bg-surface p-3.5 pb-2.5` with the composer shadow from section 2.
- Textarea on top, full width, 14.5px, no border, `placeholder:text-ink-3`. Placeholder:
  `chat.placeholder` on an empty chat, `chat.replyPlaceholder` once there are turns.
- Toolbar row under it (`mt-1.5 flex items-center gap-1.5`), in this order:
  attach (36px icon button) → `Skills` pill (only if a skills picker exists today, otherwise skip) →
  `Web` toggle pill (only if a web toggle exists today, otherwise skip) → spacer →
  `ModelEffortPicker` restyled as a ghost text button `h-8 px-2.5 text-xs text-ink-2` with chevron →
  send button 36px round `bg-primary text-white` (stop button: same size, `bg-ink text-paper`).
- Pills: `h-8 px-3 rounded-full border border-line text-xs text-ink-2`; active pill
  `border-violet-line bg-violet-tint text-violet-ink font-semibold`.
- Pending attachment chips, queue list and the approval card keep their logic; restyle with the new tokens
  (approval card: `rounded-[14px] border border-line bg-surface`, primary button flat violet).
- Disclaimer under the composer: 11px `text-ink-3`, centered.

### 5.8 Empty chat (`ChatPage.tsx`, the `empty && !isLoading` branch)

- Vertically centered block, max width 720px:
  - `<Logo className="h-7 mb-6" />`
  - `h1` `t('chat.greeting')`, 28px semibold, `tracking-tight`, `text-ink`.
  - `p` `t('chat.emptyBody')`, 14px `text-ink-2`, `mt-2`.
  - The composer directly below (`mt-7`), not at the bottom of the screen.
  - Starters BELOW the composer as a 2×2 grid (`grid-cols-1 sm:grid-cols-2 gap-2.5 mt-5`); each starter is a
    card button `rounded-[14px] border border-line bg-surface p-3.5 text-start hover:border-[#D6D1C7]
    hover:bg-paper-2`, with a 32px icon tile (`rounded-[10px] bg-paper-3 text-ink-2`) and the label 13.5px
    semibold. Icons: search → `GlobeIcon`, document → `EditIcon`, file → `PaperclipIcon`, compare → `CodeIcon`
    or a new `CompareIcon` (two stacked bars).

### 5.9 Other pages (Files, Memory, Skills, Settings, Admin)

- `PageHeader.tsx`: `px-10 pt-10 pb-6`, title 24px semibold `text-ink`, subtitle 14px `text-ink-2`,
  actions on the inline-end. Content area `px-10 pb-10`, max width 1100px.
- `FilesPage.tsx`: toolbar with search `.field` (max 320px) and filter pills (All, Uploaded, Created by agent)
  **only if the file data already exposes the source**; otherwise just All + type filters
  (Documents, Spreadsheets, Images, Other) derived from the extension. Table: `rounded-[14px] border
  border-line bg-surface`, header `bg-paper-3 text-[11px] uppercase tracking-[0.06em] text-ink-3`
  (Arabic: no uppercase), rows 56px with the badge from 5.5, name, size, updated date, and a download icon
  button. Row hover `bg-paper-2`.
- Memory, Skills, Settings, Admin: no layout change; they pick up the tokens through `.card`, `.field`,
  `.btn-primary`, `.btn-ghost`. Replace any hard-coded `secondary-*` greys in those pages with the new
  `ink-*` / `line` / `paper-*` tokens.
- `AuthLayout.tsx` (login/register): `bg-paper`, card `rounded-[20px] border border-line bg-surface p-8`,
  flat primary button. No other change.

### 5.10 Mobile (< 768px)

- Rail becomes a bottom tab bar: 64px tall + `env(safe-area-inset-bottom)`, `bg-rail`, 5 items
  (Chat, Files, Memory, Skills, Settings), each ≥44px wide, icon + 10px label. New chat moves into the chat header.
- Conversations panel becomes a slide-in drawer from the inline-start, opened by a menu icon button in the
  conversation header, with a `bg-glassy-overlay` scrim; Esc and scrim click close it; focus is trapped
  while open and returned to the menu button on close.
- Conversation header on mobile: menu button, title (truncated, centered), new-chat button.
- Composer: full width minus 12px gutters, sticky above the tab bar.
- Workspace: full-screen overlay (already the behavior; keep it).

## 6. Order of work (one commit per phase is fine, but do not commit unless the user asks)

1. Tokens + base component classes in `styles.css` (section 2). Build + lint.
2. `groupConversations.ts`, `NavRail.tsx`, `ConversationList.tsx`, `AppShell.tsx`, delete `Sidebar.tsx`
   (5.1–5.2). Build + lint.
3. Conversation header, thread, activity pill, file card (5.3–5.5). Build + lint.
4. Workspace tabs (5.6). Build + lint.
5. Composer + empty state (5.7–5.8). Build + lint.
6. Other pages + auth (5.9). Build + lint.
7. Mobile (5.10). Build + lint.
8. i18n pass: confirm every key in section 4 exists in both files, and grep for any hard-coded English string
   you introduced (`grep -rn '>[A-Z][a-z]' frontend/src/components frontend/src/pages` and review hits).

## 7. Acceptance checklist (verify each one by running the app, `cd frontend && npm run dev`)

- [ ] English LTR and Arabic RTL both render the three-zone layout mirrored correctly (rail on the start side).
- [ ] Light and dark themes both look intentional; no leftover cold-grey `secondary-*` surfaces in the chat.
- [ ] Sending a message streams; the activity pill shows the live step with a spinner, then collapses to
      the summary with a green check.
- [ ] A background run started in chat A shows "Running" on chat A's row while you are in chat B, and clears when it finishes.
- [ ] A written .docx opens in the workspace; the file card gets the violet selected ring; the thread narrows to 600px.
- [ ] Workspace tabs: Files lists every produced file; Sources appears only after a web search; Steps shows the trail.
- [ ] Approval card (write_file / run_python) still works: approve and reject.
- [ ] Branch pill shows on branched conversations; edit-and-resend still works.
- [ ] Search in the conversations panel filters live; Cmd/Ctrl+K focuses it.
- [ ] Empty chat shows greeting → composer → starters; clicking a starter sends it.
- [ ] At 390px wide: bottom tab bar, drawer opens and closes with Esc, composer usable, workspace full screen.
- [ ] Keyboard only: every control reachable with Tab, visible focus ring, icon buttons announce a label.
- [ ] `npm run build` and `npm run lint` pass with no new warnings.

## 8. Out of scope (do NOT build)

- Pinned conversations (no backend support).
- Any new backend endpoint or field (e.g. storing step durations).
- A theme or accent picker.
- Replacing the logo or changing brand colors.

---

## 9. Round 2 fixes (from review of the first implementation)

Same ground rules as section 0. Run `cd frontend && npm run build && npm run lint` after the fixes.

### Must fix

1. **Session status is rendered twice, with different numbers.** The header shows
   "Working · 12 messages · 3.3k / 33k · 10%" and a second bar under the composer shows
   "Working · 0 messages · 2.5k / 33k · 8%".
   - Keep ONLY the header instance (section 5.3). Delete the one rendered under/inside the composer
     (`ChatPage.tsx` / `Composer.tsx`).
   - Make sure the header instance receives the real `turns`, `busy`, `queue.length` and `contextWindow`.
     "0 messages" means the second copy got the wrong turns; confirm the kept one counts correctly.

2. **Composer layout does not match 5.7.** Today the attach button sits beside the textarea, and the model
   picker lives in a separate bar underneath. Change to:
   - Row 1: the textarea alone, full width.
   - Row 2 (`mt-1.5 flex items-center gap-1.5`): attach button (36px) → `flex-1` spacer →
     `ModelEffortPicker` as a ghost text button (`h-8 px-2.5 rounded-lg text-xs text-ink-2`, label
     `qwen3.8-27b · Thorough` + chevron-down) → send button.
   - Send: 36px circle `bg-primary text-white`. While busy, stop: 36px circle `bg-ink text-paper` with
     `StopIcon`. While busy with text typed (queue), show both, send first.
   - No extra footer bar inside the composer.

3. **Language toggle is broken.** In the conversations panel header, the "ع" wraps under the globe icon and
   spills out of the circle. Render it as one pill on a single line:
   `inline-flex items-center gap-1 whitespace-nowrap h-[30px] px-2.5 rounded-full border border-line
   bg-surface text-xs font-semibold text-ink-2`. Check both languages (in Arabic the pill shows "EN").

### Should fix

4. **Many file cards flood the answer.** A turn with 7 PNGs renders 7 full-width cards.
   - 1–3 files: keep the current cards (5.5).
   - More than 3: images render as a thumbnail grid (`grid grid-cols-3 gap-2.5`, tiles `aspect-[4/3]
     rounded-xl border border-line bg-paper-4 overflow-hidden`, image `object-contain`, filename 12px
     truncated under the tile, download icon button shown on hover/focus in the tile's top-end corner,
     click opens it in the workspace). Non-image files render as compact rows (44px high, 28px badge,
     name, download button).
   - Remove the "· open in workspace" subline from every card; the subline is only the type
     (e.g. "PNG", "Word document"). The selected ring (5.5) already shows which file is open.

5. **The conversation list is mostly identical "New chat" rows.**
   - Do not list conversations that have no messages. If the list API does not return a message count,
     hide rows whose title is still the default "New chat" title AND that are not the active conversation.
     Do not change the backend.
   - Check that auto-title after the first reply is still triggered from the new layout (it was added in
     commit c6c362c); if the redesign broke it, restore it.

### Small

6. The activity pill ("Thinking…") uses a right-pointing chevron. Use chevron-down, rotated 180° when open (5.4).
7. The rail avatar shows "ME" taken from the email. Use initials from the user's display name when there is
   one (first letter of the first two words), fall back to the email's first letter.
8. Verify with an admin account that the Admin icon appears in the rail above Settings.

### Also verify (not covered by the review screenshot)

- Arabic RTL, dark mode, the workspace tabs (Preview/Files/Sources/Steps), and 390px mobile width against
  the section 7 checklist.

---

## 10. Round 3 fixes (from review of round 2)

Round 2 items 1, 2, 4, 5 and 6 are done; do not touch them. Remaining:

### Must fix

1. **Language toggle is still broken, and it moved.** It now sits in the rail, above Settings, and still renders
   the globe icon with the "ع" wrapped onto a second line under it.
   - Put it back in the conversations panel header, at the end of the logo row, next to the collapse button
     (section 5.2). On non-chat routes, where that panel is hidden, it stays in the rail.
   - In the panel: a single-line pill, `inline-flex items-center gap-1 whitespace-nowrap h-[30px] px-2.5
     rounded-full border border-line bg-surface text-xs font-semibold text-ink-2`: globe icon 14px + "ع"
     (English UI) or "EN" (Arabic UI).
   - In the rail: a 44×44 button showing ONLY the text "ع" / "EN" (no globe), `text-rail-icon
     hover:text-white text-sm font-semibold`, `aria-label` = "Switch to Arabic" / "التبديل إلى الإنجليزية"
     (add i18n keys `nav.switchLanguage` in both files).

2. **Workspace tabs are missing.** The panel shows only "Preview". Implement section 5.6 fully:
   Preview | Files (count) | Sources (count, hidden when 0) | Steps. With 7 generated images in this chat,
   Files must list all 7, and clicking one switches Preview to it. Tabs use `role="tablist"`/`role="tab"`/
   `aria-selected`, and arrow keys move between tabs (Left/Right, mirrored in RTL).

### Should fix

3. **Image preview floats in the middle of the workspace** with a large empty band above it. Align the sheet to
   the top of the body (`items-start`, `p-6`), and let images scale to the panel width
   (`max-w-full h-auto`), not centered vertically.
4. **Truncated filenames in the thumbnail grid** ("02_avg_confidence_by_test_ca…"): add `title={name}` on the
   filename, and let it wrap to 2 lines (`line-clamp-2 break-all`) instead of one truncated line.
5. **Avatar still shows "ME".** Confirm round 2 item 7: initials come from the display name. If the user has no
   display name, "ME" is wrong anyway; fall back to the first letter of the email only (one letter).

### Still to verify (send screenshots after the fixes)

- Admin icon with an admin account.
- Arabic RTL, dark mode, 390px mobile width (section 7 checklist).

---

## 11. Round 4 fixes (from review of round 3)

Round 3 items 1–3 are done (language pill, workspace tabs, top-aligned preview); do not touch them.
This round is about the **expanded activity trail** and **interim text**, visible while a run is working.

### Must fix

1. **Tool rows show raw JSON arguments.** The expanded trail shows e.g.
   `Run Python {"code":"import zipfile, glob, os\n\n# find candidate docx files\nfiles = glob.g` and
   `List files {}`. Never render raw args JSON in the row label. Per tool, show a friendly one-line detail:
   - `run_python`: first non-empty, non-comment line of `code`, in mono 12px `text-ink-3`, truncated;
     plus `· N lines`. Full code only inside the row's expanded body (existing `BlockView`), in a `pre`
     with real newlines (parse the JSON; never show `\n` escapes).
   - `list_files` / any tool whose args are `{}` or empty: no detail at all.
   - `read_file`, `write_file`, `convert_upload_to_docx`: the file name.
   - `web_search`: the query in quotes. `fetch_url`: the domain.
   - Unknown tools: the first string value of the args, truncated; never the JSON.
   Put this in one helper `toolDetail(name, args): string | null` in `lib/activityLabels.ts` and use it in
   both the trail and the workspace Steps tab.

2. **Interim narration is rendered as the answer.** Text the model writes between tool calls
   ("Let me inspect the actual file to see what's inside:", "Empty output is odd — let me check…",
   "The temp workspace is fresh…") shows as full-size answer paragraphs under the trail.
   In `AssistantTurnBlocks` (`ChatPage.tsx`), split text blocks:
   - **Interim**: any text block that is followed later in the turn by a tool/skill/reasoning block. Render it
     inside the activity trail at its position in the step order, styled as `.prose-agent--compact`
     (`text-ink-2`, 13px). It is NOT shown in the answer area.
   - **Answer**: text blocks after the last tool/skill/reasoning block. Only these render full-size.
   - While streaming, the newest text block counts as interim until the turn completes or another text
     block follows with no tool call after it; when the turn completes, re-evaluate. The answer must not jump:
     keep the answer area's min-height stable while the turn is running.
   - Stored turns (loaded from the server) use the same split.

3. **The copy button overlaps answer text.** A copy icon sits inline at the end of a paragraph line
   ("…where uploads ⧉"). Remove any per-paragraph copy button. Copy lives ONLY in the turn actions row under
   the answer (section 5.4), and that row is hidden while the turn is running.

### Should fix

4. **The expanded trail has no height limit** and pushes the answer off screen. Give the expanded container
   `max-h-[360px] overflow-y-auto` with the newest step scrolled into view while running (only if the user has
   not scrolled up inside it).
5. **Live reasoning streams as a wall of text.** Inside the trail, a reasoning block that is still open shows at
   most 4 lines (`line-clamp-4`, or `max-h-[6.5rem] overflow-hidden` with a bottom fade into `bg-surface`),
   showing the latest lines. Clicking it expands the full text. Finished reasoning rows stay collapsed as
   "Thought for Ns" (already correct).
6. **Language pill:** the "ع" sits below the globe's baseline. Add `leading-none` to the pill and center the
   glyph (`items-center`, text in its own `span`).

### Still open from earlier rounds

- Avatar still shows "ME" (round 3 item 5).
- Verify Admin icon, Arabic RTL, dark mode, 390px mobile (section 7).

---

## 12. Review loop protocol (Cursor ⇄ Claude): READ THIS AFTER EVERY ROUND

You (Cursor) implement; Claude reviews screenshots and writes the next round into this file.
Communication happens ONLY through files in `design-review/`. Never edit or delete Claude's files there.

### After you finish implementing a round

1. `cd frontend && npm run build && npm run lint` must pass.
2. Start the app (backend `fastapi dev` on :8000 + `cd frontend && npm run dev`) and sign in with the test
   account the user gave you. Use a conversation that has files, tool steps and a finished answer
   (e.g. "Wallah sho 23mal"), plus an empty new chat.
3. Take these screenshots with your browser tool (or `npx playwright screenshot`; do NOT add Playwright to
   `package.json`). Viewport 1440×900 unless stated. Save as PNG in `design-review/round-<N>/`, where
   `<N>` is the round you just implemented (the first one is `round-4`):
   - `01-en-light-chat.png`: English, light, chat with finished answer + file grid, workspace closed
   - `02-en-light-workspace.png`: same chat, workspace open on a file, Files tab visible
   - `03-en-light-trail-expanded.png`: an assistant turn with the activity trail expanded
   - `04-en-light-running.png`: a run in progress (trail pill live, stop button visible)
   - `05-en-light-empty.png`: a new empty chat (greeting, composer, starters)
   - `06-ar-light-chat.png`: Arabic UI (RTL), same chat as 01
   - `07-en-dark-chat.png`: English, dark theme, same chat as 02
   - `08-en-light-files.png`: the Files page
   - `09-mobile-chat.png`: viewport 390×844, chat
   - `10-mobile-drawer.png`: viewport 390×844, conversations drawer open
   - `11-admin-rail.png`: rail signed in as admin (skip if no admin account; say so in READY)
4. Write `design-review/round-<N>/READY` (plain text): which items of this round you completed, which you
   skipped and why, and anything you could not screenshot.
5. Stop and wait. Claude will write `design-review/round-<N>/REVIEWED` and append the next section
   ("Round <N+1> fixes") to the END of this file. When `REVIEWED` exists, implement the new section,
   then repeat from step 1 with `round-<N+1>`.
6. The loop ends when `design-review/APPROVED` exists. Then stop.

---

## 13. Round 5 fixes (from audit of round 4)

Round 4 items 1–6 are done; do not touch them.

1. **Remove legacy grey tokens.** 14 files still use `secondary-*` / `text-dark` / `bg-light` (ChatSessionBar,
   ModelEffortPicker, MemoryPage, WebSearchResults, SettingsPage, FilesPage, FetchUrlResult, AdminPage, SkillsPage,
   XlsxNativePreview, ConfirmDialog, PasswordField, DocxNativePreview, App). Map them to `ink`/`ink-2`/`ink-3`/`line`/
   `paper-*`. The document sheet inside previews stays white.
2. **Files page (5.9) is not implemented.** Add search + filter pills, restyle the table, reuse `fileBadgeClass`,
   56px rows, download icon button.
