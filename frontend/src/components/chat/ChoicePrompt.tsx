import { useRef, useState, type FormEvent } from 'react'
import { useTranslation } from 'react-i18next'

export interface ChoicePromptProps {
  question: string
  options: string[]
  /** When false, show options as static chips (past turn). */
  interactive: boolean
  onPick: (option: string) => void
}

/** Claude/GPT-style human-in-the-loop choices — vertical chips + always-on Other. */
export function ChoicePrompt({
  question,
  options,
  interactive,
  onPick,
}: ChoicePromptProps) {
  const { t } = useTranslation()
  const [otherText, setOtherText] = useState('')
  const otherInput = useRef<HTMLInputElement>(null)

  const submitOther = (event?: FormEvent) => {
    event?.preventDefault()
    const trimmed = otherText.trim()
    if (!trimmed) return
    onPick(trimmed)
    setOtherText('')
  }

  const chipClass = interactive
    ? `w-full rounded-xl border border-line bg-paper-2 px-3.5 py-2.5
        text-start text-xs font-medium text-ink transition
        hover:border-violet-line hover:bg-paper-3`
    : `w-full rounded-xl border border-line-soft bg-paper-3 px-3.5 py-2.5
        text-start text-xs text-ink-3`

  return (
    <div
      className="rounded-2xl border border-line bg-surface px-4 py-3"
      role={interactive ? 'group' : undefined}
      aria-label={t('chat.choiceTitle')}
    >
      <p className="text-sm font-medium text-ink" dir="auto">
        {question}
      </p>
      <p className="mt-0.5 text-xs text-ink-2">{t('chat.choiceHint')}</p>

      <div className="mt-3 flex flex-col items-stretch gap-2">
        {options.map((option) =>
          interactive ? (
            <button
              key={option}
              type="button"
              onClick={() => onPick(option)}
              className={chipClass}
              dir="auto"
              title={option}
            >
              {option}
            </button>
          ) : (
            <span key={option} className={chipClass} dir="auto" title={option}>
              {option}
            </span>
          ),
        )}
      </div>

      {interactive ? (
        <form
          className="mt-3 flex items-center gap-2"
          onSubmit={submitOther}
        >
          <input
            ref={otherInput}
            value={otherText}
            onChange={(event) => setOtherText(event.target.value)}
            placeholder={t('chat.choiceOtherPlaceholder')}
            aria-label={t('chat.choiceOtherPlaceholder')}
            className="field min-w-0 flex-1 !rounded-xl !px-3.5 !py-2 text-xs"
            dir="auto"
          />
          <button
            type="submit"
            disabled={!otherText.trim()}
            className="btn-primary shrink-0 !rounded-xl !px-3.5 !py-2 text-xs
              disabled:opacity-40"
          >
            {t('chat.choiceOtherSend')}
          </button>
        </form>
      ) : null}
    </div>
  )
}

/** Parse ask_user tool args (and optional result payload). */
export function askUserPayload(args: string, result?: string): {
  question: string
  options: string[]
} | null {
  const fromArgs = parsePayload(args)
  if (fromArgs && fromArgs.options.length >= 2) return fromArgs
  if (result) {
    const marker = 'Payload: '
    const index = result.lastIndexOf(marker)
    if (index >= 0) {
      const fromResult = parsePayload(result.slice(index + marker.length))
      if (fromResult && fromResult.options.length >= 2) return fromResult
    }
  }
  return fromArgs
}

function parsePayload(raw: string): { question: string; options: string[] } | null {
  if (!raw.trim()) return null
  try {
    const parsed = JSON.parse(raw) as {
      question?: unknown
      options?: unknown
    }
    const question = String(parsed.question ?? '').trim()
    const options = Array.isArray(parsed.options)
      ? parsed.options
          .map((item) => String(item).trim())
          .filter(Boolean)
          .slice(0, 8)
      : []
    if (!question && options.length === 0) return null
    return { question: question || 'Choose one:', options }
  } catch {
    return null
  }
}
