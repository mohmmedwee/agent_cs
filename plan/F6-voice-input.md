# F6 — Voice input (dictation)

**Size:** S–M (1–2 days) · **Backend:** none (v1) · **Migration:** none · **Depends on:** 00-foundation

## What the user gets
A mic button in the composer. Tap it and speak Arabic or English: the words appear in the composer as you speak,
and you review them and press send. It's built for Arabic on mobile.

## Approach
**v1 uses the browser's Web Speech API** (`SpeechRecognition` / `webkitSpeechRecognition`). There's no server,
model or cost, and it supports Arabic locales. Support: Chrome/Edge desktop and Android, Safari 14.1+ (macOS and
iOS). **Firefox: none**, so the button is hidden there.

Privacy note (put this in the README): in Chrome, audio is sent to Google's speech service. Safari uses Apple's
(on-device on recent Apple silicon). If that's unacceptable for a deployment, set `VITE_DICTATION=off` to hide
the feature. v2 (not in this plan) adds a self-hosted Whisper endpoint.

**Language:** follows the UI language. Arabic → `ar-JO` by default (Levantine; widely supported), English →
`en-US`. Settings gets a "Dictation language" select with `ar-JO, ar-SA, ar-EG, ar-AE, en-US, en-GB`, stored with
`useLocalSetting('dictation-lang')`, default "Same as interface".

## Files

| File | Change |
|---|---|
| `frontend/src/types/speech.d.ts` | **new**: minimal typings (TS lib has no `SpeechRecognition`) |
| `frontend/src/hooks/useDictation.ts` | **new** |
| `frontend/src/lib/dictation.ts` (+ test) | **new**: pure text-merging helpers |
| `frontend/src/components/chat/Composer.tsx` | mic button + interim text |
| `frontend/src/components/Icons.tsx` | `MicIcon` |
| `frontend/src/pages/SettingsPage.tsx` | dictation language select |
| `i18n` | keys below |

## Step 1: typings `types/speech.d.ts`

```ts
interface SpeechRecognitionAlternative { transcript: string; confidence: number }
interface SpeechRecognitionResult { isFinal: boolean; length: number; [index: number]: SpeechRecognitionAlternative }
interface SpeechRecognitionResultList { length: number; [index: number]: SpeechRecognitionResult }
interface SpeechRecognitionEvent extends Event { resultIndex: number; results: SpeechRecognitionResultList }
interface SpeechRecognitionErrorEvent extends Event { error: string }
interface SpeechRecognitionLike extends EventTarget {
  lang: string; continuous: boolean; interimResults: boolean; maxAlternatives: number
  start(): void; stop(): void; abort(): void
  onresult: ((e: SpeechRecognitionEvent) => void) | null
  onerror: ((e: SpeechRecognitionErrorEvent) => void) | null
  onend: (() => void) | null
  onstart: (() => void) | null
}
interface Window {
  SpeechRecognition?: new () => SpeechRecognitionLike
  webkitSpeechRecognition?: new () => SpeechRecognitionLike
}
```

## Step 2: `lib/dictation.ts` (pure, tested)

```ts
/** Join base text and spoken text with exactly one space where needed. */
export function joinSpoken(base: string, spoken: string): string {
  const s = spoken.trim()
  if (!s) return base
  if (!base || /\s$/.test(base)) return base + s
  return `${base} ${s}`
}

export function dictationLang(setting: string | null, uiLang: string): string {
  if (setting && setting !== 'auto') return setting
  return uiLang.startsWith('ar') ? 'ar-JO' : 'en-US'
}
```

Tests: an empty base, a base ending with a space or newline, whitespace-only spoken text, Arabic text, and
`dictationLang` defaults.

## Step 3: `hooks/useDictation.ts`

```ts
type DictationError = 'not-allowed' | 'no-speech' | 'network' | 'audio-capture' | 'other'

export function useDictation(opts: {
  lang: string
  onFinal: (text: string) => void        // called per finalized phrase
}): {
  supported: boolean
  listening: boolean
  interim: string                        // current not-yet-final words (display only)
  error: DictationError | null
  start: () => void
  stop: () => void
  toggle: () => void
}
```

Implementation rules:
- `supported = import.meta.env.VITE_DICTATION !== 'off' && !!(window.SpeechRecognition || window.webkitSpeechRecognition)`.
- Create the recognizer **on start()** (not on mount) with `continuous = true`, `interimResults = true`,
  `maxAlternatives = 1`, `lang = opts.lang`. Keep it in a ref.
- `onresult`: loop from `e.resultIndex` to `e.results.length`. Final results → `onFinal(transcript)`.
  Non-final ones are concatenated into `interim`.
- **Silence auto-stop:** reset an 8 s timer on every `onresult`, and when it fires call `stop()`.
- `onend`: set `listening=false`, clear `interim`, clear the timer. Chrome ends sessions by itself after about
  60 s even with `continuous`. **Don't** auto-restart (restarting surprises users and keeps the mic on).
- `onerror`: map `not-allowed | service-not-allowed` → `not-allowed`; `no-speech`, `network` and
  `audio-capture` as-is; anything else → `other`. `aborted` is ignored (it's our own `stop`).
- Clean up on unmount: `abort()` and clear the timer.
- `stop()` calls `recognizer.stop()` (which flushes the last final result), not `abort()`.

## Step 4: Composer
- **Mic button** (36px circle, `MicIcon` 18px), placed between the spacer and `ModelEffortPicker`. Render it only
  if `supported`.
  - Idle: `text-ink-2 hover:bg-paper-3`. `aria-label={t('chat.dictate')}`, `aria-pressed={false}`.
  - Listening: `bg-primary text-white`, plus a ring pulse `ring-4 ring-violet-tint animate-pulse
    motion-reduce:animate-none`. `aria-label={t('chat.stopDictation')}`, `aria-pressed={true}`.
- `onFinal = (text) => setValue((v) => joinSpoken(v, text))`, then resize the textarea (existing auto-grow).
- **Interim text:** show it inside the composer below the textarea as a single `text-ink-3 text-[14.5px]
  italic` line with `dir="auto"` and `aria-live="polite"`. Don't write interim text into the textarea value;
  it'd fight with the user's typing.
- **Send while listening:** the send handler calls `dictation.stop()` first, waits for `onend` (a promise
  resolved in the hook, max 800 ms), and then sends, so the last phrase is included.
- **Esc** in the textarea while listening stops dictation (and doesn't clear text).
- **Errors:** show a one-line hint under the composer for 4 s (`role="status"`), using the key per error. For
  `not-allowed`, the hint also says how to re-enable it (`chat.micDeniedHelp`).
- While busy (the model is answering), the mic still works. Dictating the next message and queueing it is fine.

## Step 5: `MicIcon`

```tsx
export const MicIcon: Icon = (props) => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.75}
    strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" {...props}>
    <rect x="9" y="3" width="6" height="11" rx="3" />
    <path d="M5 11a7 7 0 0 0 14 0M12 18v3" />
  </svg>
)
```

## Step 6: Settings
Add a "Dictation language" select under the language setting: "Same as interface" (value `auto`), then the six
locales, with labels in the UI language. Hide the whole row when `!supported`.

## i18n

| key | en | ar |
|---|---|---|
| `chat.dictate` | Dictate | إملاء صوتي |
| `chat.stopDictation` | Stop dictation | إيقاف الإملاء |
| `chat.listening` | Listening… | جارٍ الاستماع… |
| `chat.micDenied` | Microphone access is blocked | الوصول إلى الميكروفون محظور |
| `chat.micDeniedHelp` | Allow the microphone in your browser's site settings. | اسمح باستخدام الميكروفون من إعدادات الموقع في المتصفح. |
| `chat.noSpeech` | Didn't catch that. Try again. | لم أسمع شيئًا، حاول مرة أخرى. |
| `chat.dictationNetwork` | Speech service unavailable | خدمة التعرّف على الكلام غير متاحة |
| `chat.dictationFailed` | Dictation stopped | توقف الإملاء |
| `settings.dictationLang` | Dictation language | لغة الإملاء |
| `settings.dictationAuto` | Same as interface | نفس لغة الواجهة |

## Tests
- vitest: `joinSpoken`, `dictationLang`.
- Hook logic is browser-bound. Test it manually (below). Optionally add a fake `SpeechRecognition` class in a
  vitest `jsdom` test for the silence timer and error mapping.

## Manual test plan
1. Chrome desktop, Arabic UI: dictate a sentence in Arabic. Interim words show greyed, and the final text lands RTL
   in the composer.
2. English UI, English speech; then the Settings override to `ar-EG` works.
3. Say nothing for 8 s: it stops by itself. Press Esc while listening: it stops, and the text is kept.
4. Press send mid-sentence: the last phrase is included in the sent message.
5. Deny mic permission: the hint appears, and the button returns to idle.
6. Firefox: no mic button and no console errors. `VITE_DICTATION=off` also hides it.
7. Android Chrome and iOS Safari at 390px: the button is reachable above the tab bar and works.

## Done when
- [ ] Tests pass; `scripts/check.sh` is green; manual plan 1–7 passes.
- [ ] README has the privacy note and the `VITE_DICTATION` flag.
