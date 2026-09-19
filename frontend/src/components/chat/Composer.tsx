import { useEffect, useRef, useState, type KeyboardEvent } from 'react'
import { useTranslation } from 'react-i18next'

import { ModelEffortPicker } from '@/components/chat/ModelEffortPicker'
import {
  ApprovalDiffCard,
  type ApprovalCard,
} from '@/components/chat/ApprovalDiffCard'
import {
  ComposerPlusMenu,
  type ComposerTools,
} from '@/components/chat/ComposerPlusMenu'
import {
  CloseIcon,
  SendIcon,
  SpinnerIcon,
  StopIcon,
} from '@/components/Icons'
import type { Effort, StoredFile } from '@/types'

export interface ComposerApproval {
  callId: string
  toolName: string
  fileName: string
  pending: boolean
  card?: ApprovalCard | null
  onAllow: () => void
  onDeny: () => void
}

interface Props {
  busy: boolean
  uploading: boolean
  queue: string[]
  onSend: (text: string, tools: ComposerTools) => void
  onStop: () => void
  onAttach: (files: File[]) => void
  onRemoveQueued: (index: number) => void
  /** Uploaded files waiting to be sent with the next message. */
  pendingAttachments?: StoredFile[]
  onRemoveAttachment?: (fileId: string) => void
  /** When set, composer is editing a past prompt instead of a new send. */
  editing?: { text: string; onCancel: () => void } | null
  /** HITL: Allow / Deny for gated tools, shown above the text box. */
  approval?: ComposerApproval | null
  model?: string | null
  effort?: Effort
  onModelChange?: (model: string | null) => void
  onEffortChange?: (effort: Effort) => void
  /** Tighter padding when centered in the empty-state layout. */
  compact?: boolean
  /** Empty chat uses reply vs ask placeholder. */
  emptyChat?: boolean
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
  model = null,
  effort = 'xhigh',
  onModelChange,
  onEffortChange,
  compact = false,
  emptyChat = false,
}: Props) {
  const { t } = useTranslation()
  const [text, setText] = useState('')
  const [tools, setTools] = useState<ComposerTools>({
    webSearch: true,
    research: false,
    skill: null,
  })
  const textarea = useRef<HTMLTextAreaElement>(null)

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

  const applyTools = (next: ComposerTools) => {
    setTools(next)
    queueMicrotask(() => textarea.current?.focus())
  }

  const submit = () => {
    if (approval) return
    // Drop a typed slash prefix if the chip already owns that skill.
    let trimmed = text.trim()
    if (tools.skill) {
      trimmed = trimmed
        .replace(new RegExp(`^/${tools.skill}(?=\\s|$)\\s*`), '')
        .trim()
    }
    const skill = tools.skill
    if (!trimmed && pendingAttachments.length === 0 && !skill) return
    // Bubble shows `/skill …`; chip itself is not editable text.
    const message = skill
      ? trimmed
        ? `/${skill} ${trimmed}`
        : `/${skill}`
      : trimmed
    onSend(message, { ...tools, skill })
    setText('')
    setTools((prev) => ({ ...prev, skill: null }))
  }

  const onKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === 'Escape' && editing) {
      event.preventDefault()
      editing.onCancel()
      setText('')
      return
    }
    if (approval) return
    // Backspace on empty input clears the slash skill token (Claude-style).
    if (
      event.key === 'Backspace' &&
      !text &&
      tools.skill &&
      !event.nativeEvent.isComposing
    ) {
      event.preventDefault()
      setTools((prev) => ({ ...prev, skill: null }))
      return
    }
    if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault()
      submit()
    }
  }

  const canSubmit =
    (Boolean(text.trim()) ||
      pendingAttachments.length > 0 ||
      Boolean(tools.skill)) &&
    !approval
  const sendLabel = editing
    ? t('chat.saveEdit')
    : busy
      ? t('chat.queue')
      : t('chat.send')
  const showQueueSend = busy && !editing && canSubmit && !approval

  return (
    <div className={`relative z-20 shrink-0 ${compact ? '' : ''}`}>
      <div className="relative mx-auto w-full space-y-2">
        {queue.length > 0 && (
          <div className="flex flex-wrap gap-2 px-1">
            <span className="self-center text-xs font-medium text-ink-2">
              {t('chat.queued', { count: queue.length })}
            </span>
            {queue.map((item, index) => (
              <button
                key={`${index}-${item.slice(0, 24)}`}
                type="button"
                onClick={() => onRemoveQueued(index)}
                title={t('chat.removeQueued')}
                className="group inline-flex max-w-[14rem] items-center gap-1.5 rounded-full
                  border border-line bg-surface px-3 py-1 text-xs text-ink
                  transition hover:border-error-200 hover:text-error"
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
            className="flex items-center justify-between rounded-2xl border border-line
              bg-paper-3 px-3.5 py-2 text-xs text-ink-2"
          >
            <span>{t('chat.editingPrompt')}</span>
            <button
              type="button"
              onClick={() => {
                editing.onCancel()
                setText('')
              }}
              className="font-medium text-ink underline-offset-2 hover:underline"
            >
              {t('chat.cancelEdit')}
            </button>
          </div>
        )}

        {approval && (
          <div
            className="rounded-2xl border border-line bg-surface px-4 py-3"
            role="alertdialog"
            aria-label={t('chat.approvalTitle')}
          >
            <p className="text-sm font-medium text-ink">{t('chat.approvalTitle')}</p>
            {approval.card ? (
              <ApprovalDiffCard card={approval.card} />
            ) : (
              <p className="mt-0.5 text-xs text-ink-2" dir="auto">
                {approval.toolName === 'run_python'
                  ? t('chat.approvalRunPython')
                  : approval.toolName === 'convert_upload_to_docx'
                    ? t('chat.approvalConvert', { name: approval.fileName })
                    : approval.toolName === 'edit_docx'
                      ? t('chat.approvalEdit', { name: approval.fileName })
                      : t('chat.approvalWrite', { name: approval.fileName })}
              </p>
            )}
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
                className="rounded-xl border border-line bg-surface px-4 py-2
                  text-xs font-medium text-ink-2 transition hover:border-error-200
                  hover:text-error disabled:opacity-50"
              >
                {t('chat.deny')}
              </button>
            </div>
          </div>
        )}

        <div
          className={`rounded-[20px] border bg-surface p-3.5 transition
            shadow-[var(--shadow-composer)]
            ${
              approval
                ? 'border-violet-line'
                : 'border-[#E0DCD3] focus-within:border-violet-line dark:border-line'
            }`}
        >
          {pendingAttachments.length > 0 && (
            <div className="mb-2 flex flex-wrap gap-1.5">
              {pendingAttachments.map((file) => (
                <button
                  key={file.id}
                  type="button"
                  onClick={() => onRemoveAttachment?.(file.id)}
                  title={t('chat.removeAttachment')}
                  className="group inline-flex max-w-[14rem] items-center gap-1.5 rounded-full
                    border border-line bg-paper-3 px-2.5 py-1 text-[11px]
                    font-medium text-ink-2 transition hover:border-error-200
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

          <div className="flex items-start gap-2">
            {tools.skill ? (
              <button
                type="button"
                onClick={() => setTools((prev) => ({ ...prev, skill: null }))}
                title={t('chat.clearSkill')}
                className="mt-1 shrink-0 font-mono text-[14.5px] font-medium text-primary
                  transition hover:opacity-70"
              >
                /{tools.skill}
              </button>
            ) : null}
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
                  : tools.skill
                    ? t('chat.skillPlaceholder')
                    : editing
                      ? t('chat.editPlaceholder')
                      : pendingAttachments.length > 0
                        ? t('chat.attachPlaceholder')
                        : busy
                          ? t('chat.queuePlaceholder')
                          : emptyChat
                            ? t('chat.placeholder')
                            : t('chat.replyPlaceholder')
              }
              dir="auto"
              className="max-h-[200px] min-w-0 flex-1 resize-none bg-transparent py-1
                text-[14.5px] leading-relaxed outline-none placeholder:text-ink-3
                disabled:cursor-not-allowed disabled:opacity-70"
            />
          </div>

          <div className="mt-1.5 flex items-center gap-1.5">
            <ComposerPlusMenu
              uploading={uploading}
              disabled={Boolean(editing) || Boolean(approval)}
              tools={tools}
              onToolsChange={applyTools}
              onAttach={onAttach}
            />

            <div className="min-w-0 flex-1" />

            {onModelChange && onEffortChange ? (
              <ModelEffortPicker
                model={model}
                effort={effort}
                onModelChange={onModelChange}
                onEffortChange={onEffortChange}
                variant="composer"
              />
            ) : null}

            {showQueueSend ? (
              <button
                type="button"
                onClick={submit}
                aria-label={t('chat.queue')}
                className="inline-flex size-9 shrink-0 items-center justify-center rounded-full
                  bg-primary text-white transition hover:bg-primary-600"
              >
                <SendIcon width={16} height={16} className="rtl:-scale-x-100" />
              </button>
            ) : null}

            {busy && !editing ? (
              <button
                type="button"
                onClick={onStop}
                aria-label={t('chat.stop')}
                className="inline-flex size-9 shrink-0 items-center justify-center rounded-full
                  bg-ink text-paper transition hover:opacity-90"
              >
                <StopIcon width={16} height={16} />
              </button>
            ) : (
              <button
                type="button"
                onClick={submit}
                disabled={!canSubmit}
                aria-label={sendLabel}
                className="inline-flex size-9 shrink-0 items-center justify-center rounded-full
                  bg-primary text-white transition hover:bg-primary-600 disabled:opacity-40"
              >
                <SendIcon width={16} height={16} className="rtl:-scale-x-100" />
              </button>
            )}
          </div>
        </div>

        <p className="px-1 text-center text-[11px] text-ink-3">{t('chat.disclaimer')}</p>
      </div>
    </div>
  )
}
