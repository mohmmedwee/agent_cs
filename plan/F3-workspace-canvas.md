# F3 — Workspace canvas: HTML, Markdown, code, JSON, CSV, SVG previews

**Size:** M (2–3 days) · **Backend:** small · **Migration:** none · **Depends on:** 00-foundation

## What the user gets
When the agent writes a web page, Markdown, code, JSON, CSV or SVG, the workspace shows it properly:
- an HTML page runs live, in a sandbox;
- Markdown renders, with a Rendered/Source toggle;
- code shows in monospace with line numbers;
- JSON is pretty-printed;
- CSV is a table;
- SVG is drawn as an image.

It also fixes the round-5 bug where an English document in the Arabic UI is right-aligned.

## Current state
- `ArtifactPanel` (`frontend/src/components/chat/DocumentPreview.tsx:451`) branches on
  `isImage / isDocx / isXlsx / isPptx`. **Everything else** is fetched from `GET /api/files/{id}/preview` and
  rendered through `<Markdown text={body}>` on a white sheet (~L671). A `.py` or `.html` file therefore renders
  as Markdown, which mangles it.
- `routes/files.py:73` `preview_file` returns `{id, name, text[:12_000], truncated}`.
- `write_file` already stores `.html .md .json .csv .xml` (and any other extension) as text.
- `Artifact` (`ArtifactContext.tsx`) = `{ fileId, name, content? }`. `content` is the write_file args, so a
  just-written file previews without a fetch.
- The white sheet inherits `dir="rtl"` from `<html>` in Arabic, which causes the RTL bug.

## Security model for HTML (read this first)
The HTML comes from the model, and the model can be steered by web pages it read (prompt injection), so treat
it as **hostile**:
- Render it only in `<iframe sandbox="allow-scripts" srcdoc={html}>`. **Never** add `allow-same-origin`.
  Without it, the frame gets an opaque origin: no access to our cookies, `localStorage`, or `/api` with
  credentials, and no access to `window.parent`'s DOM.
- Also no `allow-top-navigation`, `allow-popups-to-escape-sandbox` or `allow-forms`, and add
  `referrerPolicy="no-referrer"`.
- Inject a CSP `<meta>` at the top of `srcdoc` to block exfiltration via network requests:
  `default-src 'none'; img-src data: blob:; style-src 'unsafe-inline'; script-src 'unsafe-inline';
  font-src data:; media-src data: blob:`. The page can run its own inline JS but can't fetch or load anything
  remote. Document that pages needing a CDN library won't work in the preview; they still download fine.
- "Open in new tab" uses a `blob:` URL of the **same CSP-wrapped** HTML, opened with
  `window.open(url, '_blank', 'noopener,noreferrer')`. A blob URL inherits our origin, so the CSP meta is what
  protects that path too: without `connect-src` it can't call `/api`. Revoke the URL after 60 s.
- SVG is **never** inlined into our DOM (inline SVG can carry script). Render it via `<img src={blobUrl}>`, where
  scripts don't run.

## Files

| File | Change |
|---|---|
| `src/agent_console/schemas/files.py` | `FilePreviewResponse.kind` |
| `src/agent_console/api/routes/files.py` | `kind` + a per-kind size cap |
| `frontend/src/lib/previewKind.ts` (+ `.test.ts`) | **new** |
| `frontend/src/lib/csv.ts` (+ `.test.ts`) | **new**: tiny RFC-4180 parser |
| `frontend/src/lib/htmlSandbox.ts` | **new**: `wrapWithCsp(html)` |
| `frontend/src/components/chat/previews/HtmlPreview.tsx` | **new** |
| `frontend/src/components/chat/previews/CodePreview.tsx` | **new** (code + JSON) |
| `frontend/src/components/chat/previews/CsvPreview.tsx` | **new** |
| `frontend/src/components/chat/previews/SvgPreview.tsx` | **new** |
| `frontend/src/components/chat/previews/SourceToggle.tsx` | **new** |
| `frontend/src/components/chat/DocumentPreview.tsx` | use `previewKind`, the new previews, `dir="auto"` |
| `frontend/src/lib/api.ts` | preview response type gets `kind` |
| `i18n/en.json`, `ar.json` | keys below |

## Step 1: backend `kind` and cap

`schemas/files.py`:

```python
PreviewKind = Literal["html", "markdown", "code", "json", "csv", "svg", "text"]

class FilePreviewResponse(BaseModel):
    id: UUID
    name: str
    text: str
    truncated: bool
    kind: PreviewKind = "text"
```

`routes/files.py`:

```python
_CODE_EXT = {".py", ".js", ".ts", ".tsx", ".jsx", ".sql", ".sh", ".css", ".yaml", ".yml",
             ".toml", ".xml", ".java", ".go", ".rs", ".c", ".cpp", ".rb", ".php"}

def _preview_kind(name: str) -> str:
    ext = Path(name).suffix.lower()
    if ext in (".html", ".htm"): return "html"
    if ext in (".md", ".markdown"): return "markdown"
    if ext == ".json": return "json"
    if ext in (".csv", ".tsv"): return "csv"
    if ext == ".svg": return "svg"
    if ext in _CODE_EXT: return "code"
    return "text"
```

Cap: `limit = 1_000_000 if kind in ("html", "svg", "csv", "json", "code") else 12_000`. A truncated HTML page is
broken, so for `html` and `svg`, if `truncated`, return an empty `text` with `truncated=True`, and the UI shows
"too large to preview, download it". The `.docx` branch stays as it is (kind `markdown`).

Mirror `_preview_kind` exactly in `lib/previewKind.ts`, since the client needs it before the fetch returns.

## Step 2: `lib/previewKind.ts`

```ts
export type PreviewKind =
  | 'image' | 'docx' | 'xlsx' | 'pptx' | 'pdf'
  | 'html' | 'markdown' | 'code' | 'json' | 'csv' | 'svg' | 'text'

const CODE = new Set(['py','js','ts','tsx','jsx','sql','sh','css','yaml','yml','toml','xml',
                      'java','go','rs','c','cpp','rb','php'])

export function previewKind(name: string): PreviewKind {
  const ext = name.toLowerCase().split('.').pop() ?? ''
  if (['png','jpg','jpeg','gif','webp'].includes(ext)) return 'image'
  if (ext === 'docx') return 'docx'
  if (ext === 'xlsx') return 'xlsx'
  if (ext === 'pptx') return 'pptx'
  if (ext === 'pdf') return 'pdf'
  if (ext === 'html' || ext === 'htm') return 'html'
  if (ext === 'md' || ext === 'markdown') return 'markdown'
  if (ext === 'json') return 'json'
  if (ext === 'csv' || ext === 'tsv') return 'csv'
  if (ext === 'svg') return 'svg'
  if (CODE.has(ext)) return 'code'
  return 'text'
}

/** Kinds whose preview needs the file's text (fetched or from write_file args). */
export const TEXT_KINDS: ReadonlySet<PreviewKind> =
  new Set(['html', 'markdown', 'code', 'json', 'csv', 'svg', 'text'])

/** Kinds with a Rendered / Source toggle. */
export const TOGGLE_KINDS: ReadonlySet<PreviewKind> = new Set(['html', 'markdown', 'svg'])
```

Test: every extension, uppercase names (`REPORT.HTML`), no extension → `text`, `archive.tar.gz` → `text`.
Keep `isImageFileName` and the others as thin wrappers (`previewKind(n) === 'image'`) so existing imports keep
working.

## Step 3: `lib/csv.ts`

`parseCsv(text: string, delimiter?: string): string[][]`:
- state machine over characters; `"` starts a quoted field; `""` inside quotes is a literal quote; newline
  inside quotes is content; `\r\n` / `\n` end rows;
- delimiter: `\t` for `.tsv`; otherwise auto-detect from the first line (`,` vs `;`, whichever occurs more
  outside quotes);
- drops one trailing empty row.

Tests: quoted commas, escaped quotes, newline inside a quote, `;` detection, empty input → `[]`.

## Step 4: `lib/htmlSandbox.ts`

```ts
const CSP = [
  "default-src 'none'", "img-src data: blob:", "style-src 'unsafe-inline'",
  "script-src 'unsafe-inline'", 'font-src data:', 'media-src data: blob:',
].join('; ')

/** Model-written HTML, wrapped so it cannot reach the network or our API. */
export function wrapWithCsp(html: string): string {
  const meta = `<meta http-equiv="Content-Security-Policy" content="${CSP}">`
  if (/<head[^>]*>/i.test(html)) return html.replace(/<head[^>]*>/i, (m) => `${m}${meta}`)
  if (/<html[^>]*>/i.test(html)) return html.replace(/<html[^>]*>/i, (m) => `${m}<head>${meta}</head>`)
  return `<!doctype html><html><head><meta charset="utf-8">${meta}</head><body>${html}</body></html>`
}
```

The CSP meta must come **before** any `<script>` in the document. Test that a page whose first line is
`<script>` still gets the meta first (the no-`<head>` branch wraps everything).

## Step 5: preview components

All of them sit inside the workspace body (`bg-paper-4 p-6`). The document ones use the existing white-sheet
classes. Put the sheet class string in one constant, `SHEET`, in `previews/sheet.ts`, since `DocumentPreview`
repeats it.

**`HtmlPreview`** `({ html, name })`:
- `const doc = useMemo(() => wrapWithCsp(html), [html])`
- ```tsx
  <iframe title={name} sandbox="allow-scripts" referrerPolicy="no-referrer" srcDoc={doc}
    className="h-[calc(100dvh-220px)] min-h-[420px] w-full rounded bg-white shadow-…" />
  ```
- The header action "Open in new tab" (see step 6) calls `openSandboxedTab(doc)`:
  ```ts
  const url = URL.createObjectURL(new Blob([doc], { type: 'text/html' }))
  window.open(url, '_blank', 'noopener,noreferrer')
  window.setTimeout(() => URL.revokeObjectURL(url), 60_000)
  ```

**`CodePreview`** `({ text, name, kind })`:
- `kind === 'json'`: `try { text = JSON.stringify(JSON.parse(text), null, 2) } catch {}` (raw on failure).
- Render `<div dir="ltr" className="overflow-auto rounded bg-white font-mono text-[12.5px] leading-[1.6]">`
  with a two-column grid per line: a line-number gutter (`select-none text-ink-3 pe-3 text-end w-10`) and the
  code (`whitespace-pre` or `whitespace-pre-wrap break-words` when wrap is on).
- Over 5,000 lines: render the first 5,000 plus "N more lines — download to see all". Don't virtualize in v1.
- Wrap toggle state lives in the component (default off for code, on for text).

**`CsvPreview`** `({ text, name })`: `parseCsv`, first row = header, render the first 500 body rows using the
xlsx preview table classes (copy them from `XlsxNativePreview.tsx`), then `workspace.moreRows`. Cells get
`dir="auto"`. Numbers (`/^-?[\d,.]+%?$/`) are `text-end tabular-nums`.

**`SvgPreview`** `({ text, name })`: build `URL.createObjectURL(new Blob([text], {type:'image/svg+xml'}))` in a
`useEffect`, revoke on cleanup, and render `<img>` on the white sheet with `max-w-full h-auto`.

**`SourceToggle`** `({ value, onChange })`: a two-button segmented control, `role="radiogroup"`, buttons
`role="radio" aria-checked`, `h-7 px-2.5 rounded-md text-xs`, selected `bg-paper-3 text-ink font-semibold`.

## Step 6: wire it into `ArtifactPanel`

1. `const kind = artifact ? previewKind(artifact.name) : 'text'`. Delete the `isImage/isDocx/isXlsx/isPptx`
   locals and use `kind` everywhere (the `tab === 'preview' && …` branches).
2. Fetch effect (~L476): fetch only when `TEXT_KINDS.has(kind)`. Otherwise clear and return. Keep the
   `artifact.content` shortcut (the write_file args already hold the exact text, so no fetch is needed). Also
   store `preview.truncated` in state (`false` when the content shortcut is used).
3. `const [view, setView] = useState<'rendered' | 'source'>('rendered')`, reset with
   `useEffect(() => setView('rendered'), [artifact?.fileId])`.
4. Sub-header row (where the badge + name + Download are, ~L640): before Download, add
   `{TOGGLE_KINDS.has(kind) && <SourceToggle value={view} onChange={setView} />}`, then for `html` an icon
   button "Open in new tab" (`ExternalIcon`, 32px) and, for all text kinds, a Copy icon button (reuse the
   `TurnCopyButton` logic; extract it to `components/chat/CopyButton.tsx`).
5. Body:
   ```tsx
   {tab === 'preview' && TEXT_KINDS.has(kind) ? (
     loading ? <Loading/> : error ? <ErrorText/> : truncatedTooLarge ? <TooLarge/> :
     view === 'source' || kind === 'code' || kind === 'json' || kind === 'text'
       ? <CodePreview text={body} name={artifact.name} kind={kind} />
       : kind === 'html' ? <HtmlPreview html={body} name={artifact.name} />
       : kind === 'csv' ? <CsvPreview text={body} name={artifact.name} />
       : kind === 'svg' ? <SvgPreview text={body} name={artifact.name} />
       : <div className={SHEET} dir="auto"><Markdown text={body} /></div>   // markdown
   ) : null}
   ```
   Plain `text` keeps using `CodePreview` with wrap on, so a `.txt` no longer goes through Markdown.
6. **RTL fix:** add `dir="auto"` to the sheet wrapper of the docx preview (`DocxNativePreview` root), the
   markdown sheet and `CodePreview`'s `text` mode. For docx, better still: set `dir` from the first strong
   character of the document text (`is_rtl` logic ported to `lib/textDirection.ts`) so a mostly-Arabic
   document with a Latin first word still goes RTL. `dir="auto"` only looks at the first strong character.

## Step 7: i18n

| key | en | ar |
|---|---|---|
| `workspace.rendered` | Rendered | معروض |
| `workspace.source` | Source | المصدر |
| `workspace.viewMode` | View | طريقة العرض |
| `workspace.openNewTab` | Open in new tab | افتح في علامة تبويب جديدة |
| `workspace.copySource` | Copy | نسخ |
| `workspace.copied` | Copied | تم النسخ |
| `workspace.wrap` | Wrap lines | التفاف الأسطر |
| `workspace.moreRows_one` / `_other` | {{count}} more row / rows | (ar: all six plural forms: zero, one, two, few, many, other) |
| `workspace.moreLines_one` / `_other` | {{count}} more line / lines | (ar six forms) |
| `workspace.tooLarge` | Too large to preview. Download it to open. | الملف أكبر من أن يُعرض. نزّله لفتحه. |

## Tests
- vitest: `previewKind`, `parseCsv`, `wrapWithCsp` (meta present, placed before the first `<script>`, all three
  branches).
- pytest: `_preview_kind` table test; the preview route returns `kind` (with a fake repo, or `@pytest.mark.db`).

## Manual test plan
1. "Make an HTML page with a button that counts clicks." It works in the workspace. In the iframe console,
   `document.cookie` throws or is empty and `fetch('/api/files')` is blocked by CSP.
2. "Make an HTML page that loads Chart.js from a CDN." The preview shows it didn't load (expected), and the
   download works in a browser.
3. A `.md` with headings and a table renders, and Source shows raw text.
4. A `.py` file shows line numbers and LTR in the Arabic UI.
5. A CSV with quoted commas renders as correct columns.
6. An English .docx in the Arabic UI is left-aligned with correct punctuation. An Arabic .docx is right-aligned.
7. An `.svg` renders, and one containing `<script>alert(1)</script>` shows no alert.

## Done when
- [ ] Tests pass; `scripts/check.sh` is green; `DocumentPreview.tsx` is **smaller** than before (the previews moved out).
- [ ] Manual plan 1–7 passes in light/dark and EN/AR.
