import { useEffect, useRef, useState, type KeyboardEvent } from 'react'
import { useTranslation } from 'react-i18next'

import { PaperclipIcon, SendIcon, SpinnerIcon, StopIcon } from '@/components/Icons'

interface Props {
  busy: boolean
  uploading: boolean
  onSend: (text: string) => void
  onStop: () => void
  onAttach: (files: File[]) => void
}

const MAX_HEIGHT = 200

export function Composer({ busy, uploading, onSend, onStop, onAttach }: Props) {
  const { t } = useTranslation()
  const [text, setText] = useState('')
  const textarea = useRef<HTMLTextAreaElement>(null)
  const picker = useRef<HTMLInputElement>(null)

  // Grow with the content up to a ceiling, then scroll.
  useEffect(() => {
    const node = textarea.current
    if (!node) return
    node.style.height = 'auto'
    node.style.height = `${Math.min(node.scrollHeight, MAX_HEIGHT)}px`
  }, [text])

  const submit = () => {
    const trimmed = text.trim()
    if (!trimmed || busy) return
    onSend(trimmed)
    setText('')
  }

  const onKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    // Enter sends; Shift+Enter is a newline. Composition check keeps IME
    // candidate selection from firing a send.
    if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault()
      submit()
    }
  }

  return (
    <div className="border-t border-secondary-200 bg-surface px-4 py-3">
      <div
        className="mx-auto flex max-w-3xl items-end gap-2 rounded-2xl border
          border-secondary-200 bg-canvas p-2 transition focus-within:border-primary-300"
      >
        <input
          ref={picker}
          type="file"
          multiple
          hidden
          onChange={(event) => {
            const chosen = Array.from(event.target.files ?? [])
            if (chosen.length) onAttach(chosen)
            event.target.value = ''
          }}
        />
        <button
          type="button"
          onClick={() => picker.current?.click()}
          disabled={uploading}
          aria-label={t('chat.attach')}
          className="rounded-xl p-2 text-secondary transition hover:bg-secondary-100
            hover:text-dark disabled:opacity-50"
        >
          {uploading ? (
            <SpinnerIcon width={19} height={19} />
          ) : (
            <PaperclipIcon width={19} height={19} />
          )}
        </button>

        <textarea
          ref={textarea}
          value={text}
          onChange={(event) => setText(event.target.value)}
          onKeyDown={onKeyDown}
          rows={1}
          placeholder={t('chat.placeholder')}
          dir="auto"
          className="max-h-[200px] flex-1 resize-none bg-transparent py-2 text-sm
            leading-relaxed outline-none placeholder:text-secondary-400"
        />

        {busy ? (
          <button
            type="button"
            onClick={onStop}
            aria-label={t('chat.stop')}
            className="rounded-xl bg-secondary-100 p-2 text-dark transition
              hover:bg-secondary-200"
          >
            <StopIcon width={19} height={19} />
          </button>
        ) : (
          <button
            type="button"
            onClick={submit}
            disabled={!text.trim()}
            aria-label={t('chat.send')}
            className="rounded-xl bg-primary p-2 text-white transition
              hover:bg-primary-600 disabled:opacity-40"
          >
            <SendIcon width={19} height={19} className="rtl:-scale-x-100" />
          </button>
        )}
      </div>
    </div>
  )
}
