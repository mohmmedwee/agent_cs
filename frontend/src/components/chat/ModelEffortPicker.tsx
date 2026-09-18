import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useQuery } from '@tanstack/react-query'

import { CheckIcon, ChevronIcon } from '@/components/Icons'
import { api } from '@/lib/api'
import type { Effort } from '@/types'

const EFFORTS: Effort[] = ['minimal', 'low', 'medium', 'xhigh']

interface Props {
  model: string | null
  effort: Effort
  onModelChange: (model: string | null) => void
  onEffortChange: (effort: Effort) => void
  /** Quiet Workbench composer toolbar style. */
  variant?: 'default' | 'composer'
}

function shortModelName(id: string): string {
  const leaf = id.split('/').pop() ?? id
  return leaf.length > 22 ? `${leaf.slice(0, 20)}…` : leaf
}

function effortLabelKey(level: Effort): string {
  if (level === 'xhigh') return 'settings.effortXhigh'
  return `settings.effort${level.charAt(0).toUpperCase()}${level.slice(1)}`
}

function effortHelpKey(level: Effort): string {
  if (level === 'xhigh') return 'settings.effortXhighHelp'
  return `settings.effort${level.charAt(0).toUpperCase()}${level.slice(1)}Help`
}

/**
 * Claude-style model / thinking-effort menu, anchored to the composer.
 */
export function ModelEffortPicker({
  model,
  effort,
  onModelChange,
  onEffortChange,
  variant = 'default',
}: Props) {
  const { t } = useTranslation()
  const [open, setOpen] = useState(false)
  const [panel, setPanel] = useState<'main' | 'effort'>('main')
  const root = useRef<HTMLDivElement>(null)

  const { data } = useQuery({
    queryKey: ['models'],
    queryFn: api.models,
    staleTime: 60_000,
  })
  const models = data?.models ?? []
  const activeModel = model ?? data?.current ?? models[0]?.id ?? null

  useEffect(() => {
    if (!open) return
    const onPointer = (event: MouseEvent) => {
      if (!root.current?.contains(event.target as Node)) {
        setOpen(false)
        setPanel('main')
      }
    }
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        setOpen(false)
        setPanel('main')
      }
    }
    document.addEventListener('mousedown', onPointer)
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('mousedown', onPointer)
      document.removeEventListener('keydown', onKey)
    }
  }, [open])

  const triggerClass =
    variant === 'composer'
      ? `inline-flex h-8 max-w-[16rem] items-center gap-1.5 rounded-lg px-2.5
          text-xs text-ink-2 transition hover:bg-paper-3 hover:text-ink`
      : `inline-flex max-w-[13rem] items-center gap-1.5 rounded-full
          border border-line bg-surface px-2.5 py-1 text-[11px]
          font-medium text-ink transition hover:border-line
          hover:bg-paper-3`

  return (
    <div ref={root} className="relative z-50">
      <button
        type="button"
        onClick={() => {
          setOpen((value) => !value)
          setPanel('main')
        }}
        aria-expanded={open}
        aria-haspopup="dialog"
        className={triggerClass}
      >
        <span className="truncate" dir="ltr">
          {activeModel ? shortModelName(activeModel) : t('chat.modelPicker')}
        </span>
        <span className="text-ink-3">·</span>
        <span className="shrink-0">{t(effortLabelKey(effort))}</span>
        <ChevronIcon
          width={12}
          height={12}
          className={`shrink-0 text-ink-3 transition-transform ${
            open ? '-rotate-90' : 'rotate-90'
          }`}
        />
      </button>

      {open && (
        <div
          role="dialog"
          aria-label={t('chat.modelPicker')}
          className="absolute bottom-[calc(100%+0.5rem)] end-0 z-50 w-[min(18.5rem,calc(100vw-2rem))]
            overflow-hidden rounded-2xl border border-line bg-surface
            shadow-xl"
        >
          {panel === 'main' ? (
            <div className="py-1.5">
              {models.length === 0 ? (
                <p className="px-3.5 py-3 text-xs text-ink-2">
                  {t('settings.modelUnavailable')}
                </p>
              ) : (
                <ul className="max-h-52 overflow-y-auto py-0.5">
                  {models.map((entry) => {
                    const selected = entry.id === activeModel
                    return (
                      <li key={entry.id}>
                        <button
                          type="button"
                          onClick={() => {
                            onModelChange(entry.id)
                            setOpen(false)
                            setPanel('main')
                          }}
                          className={`flex w-full items-start gap-2 px-3.5 py-2.5 text-start
                            transition hover:bg-paper-3 ${selected ? 'bg-paper-3' : ''}`}
                        >
                          <span className="min-w-0 flex-1">
                            <span className="block truncate text-sm font-medium text-ink" dir="ltr">
                              {shortModelName(entry.id)}
                            </span>
                            <span className="mt-0.5 block text-[11px] text-ink-2">
                              {entry.loaded
                                ? t('chat.modelLoaded')
                                : t('chat.modelAvailable')}
                            </span>
                          </span>
                          {selected ? (
                            <CheckIcon width={16} height={16} className="mt-0.5 shrink-0 text-ink" />
                          ) : null}
                        </button>
                      </li>
                    )
                  })}
                </ul>
              )}

              <div className="my-1 border-t border-line-soft" />

              <button
                type="button"
                onClick={() => setPanel('effort')}
                className="flex w-full items-center justify-between gap-2 px-3.5 py-2.5
                  text-start transition hover:bg-paper-3"
              >
                <span>
                  <span className="block text-sm font-medium text-ink">
                    {t('settings.effort')}
                  </span>
                  <span className="mt-0.5 block text-[11px] text-ink-2">
                    {t('chat.effortThinking')}
                  </span>
                </span>
                <span className="inline-flex shrink-0 items-center gap-1 text-xs font-medium text-ink-2">
                  {t(effortLabelKey(effort))}
                  <ChevronIcon
                    width={12}
                    height={12}
                    className="text-ink-2 rtl:-scale-x-100"
                  />
                </span>
              </button>
            </div>
          ) : (
            <div className="py-1.5">
              <button
                type="button"
                onClick={() => setPanel('main')}
                className="flex w-full items-center gap-2 px-3.5 py-2 text-xs font-medium
                  text-ink-2 transition hover:bg-paper-3 hover:text-ink"
              >
                <ChevronIcon
                  width={12}
                  height={12}
                  className="rotate-180 rtl:rotate-0 rtl:scale-x-100"
                />
                {t('settings.effort')}
              </button>
              <ul>
                {EFFORTS.map((level) => {
                  const selected = effort === level
                  return (
                    <li key={level}>
                      <button
                        type="button"
                        onClick={() => {
                          onEffortChange(level)
                          setOpen(false)
                          setPanel('main')
                        }}
                        className={`flex w-full items-start gap-2 px-3.5 py-2.5 text-start
                          transition hover:bg-paper-3 ${selected ? 'bg-paper-3' : ''}`}
                      >
                        <span className="min-w-0 flex-1">
                          <span className="block text-sm font-medium text-ink">
                            {t(effortLabelKey(level))}
                          </span>
                          <span className="mt-0.5 block text-[11px] text-ink-2">
                            {t(effortHelpKey(level))}
                          </span>
                        </span>
                        {selected ? (
                          <CheckIcon
                            width={16}
                            height={16}
                            className="mt-0.5 shrink-0 text-ink"
                          />
                        ) : null}
                      </button>
                    </li>
                  )
                })}
              </ul>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
