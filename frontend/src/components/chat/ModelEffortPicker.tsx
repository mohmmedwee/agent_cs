import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useQuery } from '@tanstack/react-query'

import { CheckIcon, ChevronIcon } from '@/components/Icons'
import { api } from '@/lib/api'
import type { Effort } from '@/types'

const EFFORTS: Effort[] = ['minimal', 'low', 'medium', 'high']

interface Props {
  model: string | null
  effort: Effort
  onModelChange: (model: string | null) => void
  onEffortChange: (effort: Effort) => void
}

function shortModelName(id: string): string {
  const leaf = id.split('/').pop() ?? id
  return leaf.length > 22 ? `${leaf.slice(0, 20)}…` : leaf
}

function effortLabelKey(level: Effort): string {
  return `settings.effort${level.charAt(0).toUpperCase()}${level.slice(1)}`
}

function effortHelpKey(level: Effort): string {
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
        className="inline-flex max-w-[13rem] items-center gap-1.5 rounded-full
          border border-primary-100 bg-surface px-2.5 py-1 text-[11px]
          font-medium text-dark shadow-sm transition hover:border-primary-300
          hover:bg-primary-25"
      >
        <span className="truncate" dir="ltr">
          {activeModel ? shortModelName(activeModel) : t('chat.modelPicker')}
        </span>
        <span className="text-secondary-400">·</span>
        <span className="shrink-0 text-primary">{t(effortLabelKey(effort))}</span>
        <ChevronIcon
          width={11}
          height={11}
          className={`shrink-0 text-secondary transition-transform ${open ? 'rotate-90' : ''} rtl:-scale-x-100`}
        />
      </button>

      {open && (
        <div
          role="dialog"
          aria-label={t('chat.modelPicker')}
          className="absolute bottom-[calc(100%+0.5rem)] end-0 z-50 w-[min(18.5rem,calc(100vw-2rem))]
            overflow-hidden rounded-2xl border border-secondary-200 bg-surface
            shadow-xl"
        >
          {panel === 'main' ? (
            <div className="py-1.5">
              {models.length === 0 ? (
                <p className="px-3.5 py-3 text-xs text-secondary">
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
                            transition hover:bg-primary-25 ${selected ? 'bg-primary-25/70' : ''}`}
                        >
                          <span className="min-w-0 flex-1">
                            <span className="block truncate text-sm font-medium text-dark" dir="ltr">
                              {shortModelName(entry.id)}
                            </span>
                            <span className="mt-0.5 block text-[11px] text-secondary">
                              {entry.loaded
                                ? t('chat.modelLoaded')
                                : t('chat.modelAvailable')}
                            </span>
                          </span>
                          {selected ? (
                            <CheckIcon width={16} height={16} className="mt-0.5 shrink-0 text-primary" />
                          ) : null}
                        </button>
                      </li>
                    )
                  })}
                </ul>
              )}

              <div className="my-1 border-t border-secondary-100" />

              <button
                type="button"
                onClick={() => setPanel('effort')}
                className="flex w-full items-center justify-between gap-2 px-3.5 py-2.5
                  text-start transition hover:bg-primary-25"
              >
                <span>
                  <span className="block text-sm font-medium text-dark">
                    {t('settings.effort')}
                  </span>
                  <span className="mt-0.5 block text-[11px] text-secondary">
                    {t('chat.effortThinking')}
                  </span>
                </span>
                <span className="inline-flex shrink-0 items-center gap-1 text-xs font-medium text-primary">
                  {t(effortLabelKey(effort))}
                  <ChevronIcon
                    width={12}
                    height={12}
                    className="text-secondary rtl:-scale-x-100"
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
                  text-secondary transition hover:bg-primary-25 hover:text-dark"
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
                          transition hover:bg-primary-25 ${selected ? 'bg-primary-25/70' : ''}`}
                      >
                        <span className="min-w-0 flex-1">
                          <span className="block text-sm font-medium text-dark">
                            {t(effortLabelKey(level))}
                          </span>
                          <span className="mt-0.5 block text-[11px] text-secondary">
                            {t(effortHelpKey(level))}
                          </span>
                        </span>
                        {selected ? (
                          <CheckIcon
                            width={16}
                            height={16}
                            className="mt-0.5 shrink-0 text-primary"
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
