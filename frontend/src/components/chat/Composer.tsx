import { useEffect, useRef, useState, type KeyboardEvent } from 'react'
import { useTranslation } from 'react-i18next'

import {
  ChatSessionBar,
  type SessionBarProps,
} from '@/components/chat/ChatSessionBar'
import { ModelEffortPicker } from '@/components/chat/ModelEffortPicker'
import { CloseIcon, PaperclipIcon, SendIcon, SpinnerIcon, StopIcon } from '@/components/Icons'
import type { Effort, StoredFile } from '@/types'

export interface ComposerApproval {
  callId: string
  fileName: string
  pending: boolean
  onAllow: () => void
  onDeny: () => void
}

interface Props {
  busy: boolean
  uploading: boolean
  queue: string[]
  onSend: (text: string) => void
  onStop: () => void
  onAttach: (files: File[]) => void
  onRemoveQueued: (index: number) => void
  /** Uploaded files waiting to be sent with the next message. */
  pendingAttachments?: StoredFile[]
  onRemoveAttachment?: (fileId: string) => void
  /** When set, composer is editing a past prompt instead of a new send. */
  editing?: { text: string; onCancel: () => void } | null
  /** HITL: Allow / Deny for write_file, shown above the text box. */
  approval?: ComposerApproval | null
  /** Status + context meter footer inside the composer shell. */
  session?: SessionBarProps | null
  model?: string | null
  effort?: Effort
  onModelChange?: (model: string | null) => void
  onEffortChange?: (effort: Effort) => void
}

const MAX_HEIGHT = 200

export function Composer({
  busy,
  uploading,
  queue,
  onSend,
  onStop,
  onAttach,
  onRemoveQueued,
  pendingAttachments = [],
  onRemoveAttachment,
  editing = null,
  approval = null,
  session = null,
  model = null,
  effort = 'medium',
  onModelChange,
  onEffortChange,
}: Props) {
  const { t } = useTranslation()
  const [text, setText] = useState('')
  const textarea = useRef<HTMLTextAreaElement>(null)
  const picker = useRef<HTMLInputElement>(null)

  useEffect(() => {
    if (editing) {
      setText(editing.text)
      textarea.current?.focus()
    }
  }, [editing])

  useEffect(() => {
    if (pendingAttachments.length > 0) {
      textarea.current?.focus()
    }
  }, [pendingAttachments.length])

  useEffect(() => {
    const node = textarea.current
    if (!node) return
    node.style.height = 'auto'
    node.style.height = `${Math.min(node.scrollHeight, MAX_HEIGHT)}px`
  }, [text])

  const submit = () => {
    if (approval) return
    const trimmed = text.trim()
    if (!trimmed && pendingAttachments.length === 0) return
    onSend(trimmed)
    setText('')
  }

  const onKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === 'Escape' && editing) {
      event.preventDefault()
      editing.onCancel()
      setText('')
      return
    }
    if (approval) return
    if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault()
      submit()
    }
  }

  const canSubmit =
    (Boolean(text.trim()) || pendingAttachments.length > 0) && !approval
  const sendLabel = editing
    ? t('chat.saveEdit')
    : busy
      ? t('chat.queue')
      : t('chat.send')

  return (
    <div className="relative z-20 shrink-0 px-4 pb-4 pt-2">
      <div
        aria-hidden
        className="pointer-events-none absolute inset-x-0 -top-10 h-10
          bg-gradient-to-t from-primary-25/90 to-transparent"
      />

      <div className="relative mx-auto max-w-3xl space-y-2">
        {queue.length > 0 && (
          <div className="flex flex-wrap gap-2 px-1">
            <span className="self-center text-xs font-medium text-secondary">
              {t('chat.queued', { count: queue.length })}
            </span>
            {queue.map((item, index) => (
              <button
                key={`${index}-${item.slice(0, 24)}`}
                type="button"
                onClick={() => onRemoveQueued(index)}
                title={t('chat.removeQueued')}
                className="group inline-flex max-w-[14rem] items-center gap-1.5 rounded-full
                  border border-primary-100 bg-surface px-3 py-1 text-xs text-dark
                  shadow-sm transition hover:border-error-200 hover:text-error"
              >
                <span className="truncate" dir="auto">
                  {item}
                </span>
                <CloseIcon width={12} height={12} className="shrink-0 opacity-50 group-hover:opacity-100" />
              </button>
            ))}
          </div>
        )}

        {editing && (
          <div
            className="flex items-center justify-between rounded-2xl border border-primary-200
              bg-primary-25 px-3.5 py-2 text-xs text-primary"
          >
            <span>{t('chat.editingPrompt')}</span>
            <button
              type="button"
              onClick={() => {
                editing.onCancel()
                setText('')
              }}
              className="font-medium underline-offset-2 hover:underline"
            >
              {t('chat.cancelEdit')}
            </button>
          </div>
        )}

        {approval && (
          <div
            className="rounded-3xl border border-primary-200 bg-surface/95 px-4 py-3
              shadow-lg backdrop-blur-md"
            role="alertdialog"
            aria-label={t('chat.approvalTitle')}
          >
            <p className="text-sm font-medium text-dark">{t('chat.approvalTitle')}</p>
            <p className="mt-0.5 text-xs text-secondary" dir="auto">
              {t('chat.approvalWrite', { name: approval.fileName })}
            </p>
            <div className="mt-3 flex flex-wrap gap-2">
              <button
                type="button"
                disabled={approval.pending}
                onClick={approval.onAllow}
                className="btn-primary !px-4 !py-2 text-xs"
              >
                {approval.pending ? <SpinnerIcon width={14} height={14} /> : null}
                {t('chat.allow')}
              </button>
              <button
                type="button"
                disabled={approval.pending}
                onClick={approval.onDeny}
                className="rounded-xl border border-secondary-200 bg-surface px-4 py-2
                  text-xs font-medium text-secondary transition hover:border-error-200
                  hover:text-error disabled:opacity-50"
              >
                {t('chat.deny')}
              </button>
            </div>
          </div>
        )}

        <div
          className={`rounded-3xl border bg-glassy shadow-lg backdrop-blur-md
            transition focus-within:shadow-md
            ${
              approval
                ? 'border-primary-200 opacity-90'
                : 'border-primary-100 focus-within:border-primary-300'
            }`}
        >
          {pendingAttachments.length > 0 && (
            <div className="flex flex-wrap gap-1.5 border-b border-primary-50/80 px-3 pt-3 pb-1">
              {pendingAttachments.map((file) => (
                <button
                  key={file.id}
                  type="button"
                  onClick={() => onRemoveAttachment?.(file.id)}
                  title={t('chat.removeAttachment')}
                  className="group inline-flex max-w-[14rem] items-center gap-1.5 rounded-full
                    border border-primary-100 bg-primary-25 px-2.5 py-1 text-[11px]
                    font-medium text-primary transition hover:border-error-200
                    hover:bg-error-50 hover:text-error"
                >
                  <span className="truncate" dir="auto">
                    {file.name}
                  </span>
                  <CloseIcon
                    width={11}
                    height={11}
                    className="shrink-0 opacity-60 group-hover:opacity-100"
                  />
                </button>
              ))}
            </div>
          )}

          <div className="flex items-end gap-2 p-2.5">
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
              disabled={uploading || Boolean(editing) || Boolean(approval)}
              aria-label={t('chat.attach')}
              className="shrink-0 rounded-2xl p-2.5 text-secondary transition
                hover:bg-primary-25 hover:text-primary disabled:opacity-50"
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
              disabled={Boolean(approval)}
              placeholder={
                approval
                  ? t('chat.approvalPlaceholder')
                  : editing
                    ? t('chat.editPlaceholder')
                    : pendingAttachments.length > 0
                      ? t('chat.attachPlaceholder')
                      : busy
                        ? t('chat.queuePlaceholder')
                        : t('chat.placeholder')
              }
              dir="auto"
              className="max-h-[200px] min-w-0 flex-1 resize-none bg-transparent py-2.5
                text-sm leading-relaxed outline-none placeholder:text-secondary-400
                disabled:cursor-not-allowed disabled:opacity-70"
            />

            {busy && !editing ? (
              <div className="flex shrink-0 items-center gap-1">
                {!approval && (
                  <button
                    type="button"
                    onClick={submit}
                    disabled={!canSubmit}
                    aria-label={t('chat.queue')}
                    className="rounded-2xl bg-primary-50 p-2.5 text-primary transition
                      hover:bg-primary-100 disabled:opacity-40"
                  >
                    <SendIcon width={19} height={19} className="rtl:-scale-x-100" />
                  </button>
                )}
                <button
                  type="button"
                  onClick={onStop}
                  aria-label={t('chat.stop')}
                  className="rounded-2xl bg-secondary-100 p-2.5 text-dark transition
                    hover:bg-secondary-200"
                >
                  <StopIcon width={19} height={19} />
                </button>
              </div>
            ) : (
              <button
                type="button"
                onClick={submit}
                disabled={!canSubmit}
                aria-label={sendLabel}
                className="shrink-0 rounded-2xl p-2.5 text-white transition
                  disabled:opacity-40"
                style={
                  canSubmit
                    ? {
                        background:
                          'linear-gradient(180deg, var(--color-primary-300), var(--color-primary))',
                      }
                    : { background: 'var(--color-primary)' }
                }
              >
                <SendIcon width={19} height={19} className="rtl:-scale-x-100" />
              </button>
            )}
          </div>

          <ChatSessionBar
            turns={session?.turns ?? []}
            busy={session?.busy ?? busy}
            awaitingApproval={session?.awaitingApproval ?? false}
            queueLength={session?.queueLength ?? queue.length}
            contextWindow={session?.contextWindow ?? 32_768}
            contextCompressed={session?.contextCompressed ?? false}
            contextSummary={session?.contextSummary ?? null}
            summarizedCount={session?.summarizedCount ?? 0}
            trailing={
              onModelChange && onEffortChange ? (
                <ModelEffortPicker
                  model={model}
                  effort={effort}
                  onModelChange={onModelChange}
                  onEffortChange={onEffortChange}
                />
              ) : null
            }
          />
        </div>
      </div>
    </div>
  )
}
