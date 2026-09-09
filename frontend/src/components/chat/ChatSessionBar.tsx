import { useEffect, useId, useRef, useState, type ReactNode } from 'react'
import { useTranslation } from 'react-i18next'

import {
  estimateModelContextTokens,
  formatTokenCount,
  sessionStatus,
  type SessionStatus,
} from '@/lib/contextEstimate'
import type { Turn } from '@/types'

export interface SessionBarProps {
  turns: Turn[]
  busy: boolean
  awaitingApproval: boolean
  queueLength: number
  contextWindow: number
  /** Older turns were folded for the model. */
  contextCompressed?: boolean
  /** Text the model sees instead of older turns. */
  contextSummary?: string | null
  /** How many leading messages are covered by the summary. */
  summarizedCount?: number
  /** e.g. model / effort picker */
  trailing?: ReactNode
}

function statusTone(status: SessionStatus): {
  dot: string
  chip: string
} {
  switch (status) {
    case 'working':
      return {
        dot: 'bg-primary animate-pulse',
        chip: 'bg-primary-50 text-primary',
      }
    case 'approval':
      return {
        dot: 'bg-warning',
        chip: 'bg-warning-50 text-warning',
      }
    case 'queued':
      return {
        dot: 'bg-primary-300',
        chip: 'bg-primary-25 text-primary-600',
      }
    default:
      return {
        dot: 'bg-success',
        chip: 'bg-success-50 text-success',
      }
  }
}

function barClass(ratio: number): string {
  if (ratio >= 0.9) return 'bg-error'
  if (ratio >= 0.7) return 'bg-warning'
  return 'bg-primary'
}

/** Compact footer strip — meant to sit inside the composer shell. */
export function ChatSessionBar({
  turns,
  busy,
  awaitingApproval,
  queueLength,
  contextWindow,
  contextCompressed = false,
  contextSummary = null,
  summarizedCount = 0,
  trailing,
}: SessionBarProps) {
  const { t } = useTranslation()
  const panelId = useId()
  const [summaryOpen, setSummaryOpen] = useState(false)
  const panelRef = useRef<HTMLDivElement>(null)
  const status = sessionStatus({ busy, awaitingApproval, queueLength })
  const { used, ratio, percent } = estimateModelContextTokens({
    turns,
    contextWindow,
    contextSummary,
    summarizedCount,
  })
  const messages = turns.length
  const tone = statusTone(status)
  const showStats = messages > 0 || busy
  const canViewSummary = contextCompressed && Boolean(contextSummary?.trim())

  useEffect(() => {
    if (!summaryOpen) return
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setSummaryOpen(false)
    }
    const onPointer = (event: MouseEvent) => {
      if (!panelRef.current?.contains(event.target as Node)) {
        setSummaryOpen(false)
      }
    }
    document.addEventListener('keydown', onKey)
    document.addEventListener('mousedown', onPointer)
    return () => {
      document.removeEventListener('keydown', onKey)
      document.removeEventListener('mousedown', onPointer)
    }
  }, [summaryOpen])

  useEffect(() => {
    if (!canViewSummary) setSummaryOpen(false)
  }, [canViewSummary])

  const statusLabel =
    status === 'ready'
      ? t('chat.statusReady')
      : status === 'working'
        ? t('chat.statusWorking')
        : status === 'approval'
          ? t('chat.statusApproval')
          : t('chat.statusQueued')

  return (
    <div className="relative">
      {summaryOpen && canViewSummary ? (
        <div
          ref={panelRef}
          id={panelId}
          role="dialog"
          aria-label={t('chat.contextSummaryTitle')}
          className="absolute bottom-full start-0 z-20 mb-2 w-[min(100%,22rem)]
            rounded-2xl border border-primary-100 bg-white p-3 shadow-lg
            shadow-primary-900/10"
        >
          <div className="mb-2 flex items-start justify-between gap-2">
            <div>
              <p className="text-xs font-semibold text-primary">
                {t('chat.contextSummaryTitle')}
              </p>
              {summarizedCount > 0 ? (
                <p className="mt-0.5 text-[11px] text-secondary">
                  {t('chat.contextSummaryMeta', { count: summarizedCount })}
                </p>
              ) : null}
            </div>
            <button
              type="button"
              onClick={() => setSummaryOpen(false)}
              className="rounded-lg px-1.5 py-0.5 text-[11px] font-medium
                text-secondary hover:bg-primary-25 hover:text-primary"
            >
              {t('chat.contextSummaryClose')}
            </button>
          </div>
          <pre
            className="max-h-48 overflow-auto whitespace-pre-wrap break-words
              rounded-xl bg-primary-25/60 px-2.5 py-2 text-[11px] leading-relaxed
              text-secondary-700"
            dir="auto"
          >
            {contextSummary}
          </pre>
        </div>
      ) : null}

      <div
        className="flex flex-wrap items-center justify-between gap-x-3 gap-y-1.5
          rounded-b-3xl border-t border-primary-50/80 bg-primary-25/40 px-3 py-2"
      >
        <div className="inline-flex min-w-0 flex-wrap items-center gap-2">
          {showStats ? (
            <>
              <span
                className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5
                  text-[11px] font-semibold tracking-wide ${tone.chip}`}
              >
                <span className={`size-1.5 rounded-full ${tone.dot}`} aria-hidden />
                {statusLabel}
              </span>
              <span className="text-[11px] text-secondary">
                {t('chat.messagesCount', { count: messages })}
              </span>
              {contextCompressed ? (
                <button
                  type="button"
                  disabled={!canViewSummary}
                  aria-expanded={summaryOpen}
                  aria-controls={canViewSummary ? panelId : undefined}
                  onClick={() => canViewSummary && setSummaryOpen((open) => !open)}
                  className="rounded-full bg-secondary-100 px-2 py-0.5 text-[11px]
                    font-medium text-secondary transition enabled:hover:bg-secondary-200
                    enabled:hover:text-secondary-800 disabled:cursor-default"
                  title={
                    canViewSummary
                      ? t('chat.contextSummaryOpenHint')
                      : t('chat.contextCompressedHint')
                  }
                >
                  {t('chat.contextCompressed')}
                </button>
              ) : null}
            </>
          ) : (
            <span className="text-[11px] text-secondary">{t('chat.composerHints')}</span>
          )}
        </div>

        <div className="ms-auto inline-flex flex-wrap items-center justify-end gap-2.5">
          {trailing}

          {showStats ? (
            <div
              className="inline-flex items-center gap-2"
              title={t('chat.contextHint')}
            >
              <span className="text-[11px] font-medium tabular-nums text-secondary">
                {t('chat.contextShort', {
                  used: formatTokenCount(used),
                  total: formatTokenCount(contextWindow),
                })}
              </span>
              <div
                className="h-1 w-14 overflow-hidden rounded-full bg-secondary-100
                  sm:w-16"
                role="meter"
                aria-valuemin={0}
                aria-valuemax={100}
                aria-valuenow={percent}
                aria-label={t('chat.contextLabel')}
              >
                <div
                  className={`h-full rounded-full transition-[width] duration-300 ${barClass(ratio)}`}
                  style={{ width: `${Math.max(4, percent)}%` }}
                />
              </div>
              <span className="w-7 text-end text-[11px] tabular-nums text-secondary">
                {percent}%
              </span>
            </div>
          ) : null}
        </div>
      </div>
    </div>
  )
}
