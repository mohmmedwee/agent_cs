import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'

import { ChevronIcon, SpinnerIcon } from '@/components/Icons'

export type ParsedSearchHit = {
  title: string
  url: string
  snippet: string
  domain: string
}

/**
 * Rehydrate the plain-text tool result into rows the UI can render.
 *
 * The model still sees the same text; only the presentation changes. Blocks
 * are title / indented URL / optional snippet, separated by a blank line —
 * that is what `SearchResult.as_line` emits.
 */
export function parseSearchResultText(result: string): ParsedSearchHit[] {
  if (!result.trim() || result.startsWith('Error:') || result.startsWith('No results')) {
    return []
  }

  return result
    .split(/\n\n+/)
    .map((block) => {
      const lines = block.split('\n').map((line) => line.trim()).filter(Boolean)
      if (lines.length < 2) return null
      const title = lines[0]
      const url = lines[1]
      if (!/^https?:\/\//i.test(url)) return null
      let domain = url
      try {
        domain = new URL(url).hostname
      } catch {
        /* keep raw */
      }
      return {
        title,
        url,
        snippet: lines.slice(2).join(' '),
        domain,
      }
    })
    .filter((hit): hit is ParsedSearchHit => hit !== null)
}

function faviconUrl(domain: string): string {
  return `https://www.google.com/s2/favicons?domain=${encodeURIComponent(domain)}&sz=32`
}

/**
 * Search results as a compact source list — title + domain, not the raw dump
 * the tool returns to the model. Matches the familiar "Searched the web …"
 * pattern so the transcript reads as research, not as a tool log.
 */
export function WebSearchResults({
  query,
  result,
  pending,
  failed,
}: {
  query: string
  result?: string
  pending: boolean
  failed: boolean
}) {
  const { t } = useTranslation()
  // Finished searches stay collapsed so the answer stays the focus.
  const [open, setOpen] = useState(false)
  const [canScrollMore, setCanScrollMore] = useState(false)
  const listRef = useRef<HTMLDivElement>(null)
  const hits = result && !failed ? parseSearchResultText(result) : []

  useEffect(() => {
    if (failed || pending) setOpen(true)
  }, [failed, pending])

  const updateScrollHint = () => {
    const node = listRef.current
    if (!node) {
      setCanScrollMore(false)
      return
    }
    setCanScrollMore(node.scrollHeight - node.scrollTop - node.clientHeight > 8)
  }

  useEffect(() => {
    updateScrollHint()
  }, [hits.length, open])

  return (
    <div className="space-y-2">
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        className="flex w-full items-center gap-1.5 text-start text-xs text-ink-2"
        aria-expanded={open}
      >
        <span>
          {pending ? t('chat.searchingWeb') : t('chat.searchedWeb')}{' '}
          <span className="font-medium text-ink-3" dir="auto">
            {query || '…'}
          </span>
          {!pending && !failed && hits.length > 0 ? (
            <span className="font-normal text-ink-2">
              {' '}
              · {t('chat.searchHitCount', { count: hits.length })}
            </span>
          ) : null}
        </span>
        {pending ? (
          <SpinnerIcon width={12} height={12} className="shrink-0" />
        ) : (
          <ChevronIcon
            width={13}
            height={13}
            className={`shrink-0 transition-transform ${open ? 'rotate-90' : ''}
              rtl:-scale-x-100`}
          />
        )}
      </button>

      {open && (
        <div className="relative">
          <div
            ref={listRef}
            onScroll={updateScrollHint}
            className={`max-h-64 overflow-y-auto rounded-2xl border border-line
              bg-surface ${failed ? 'border-error-200 bg-error-50' : ''}`}
          >
            {pending && (
              <p className="px-3.5 py-3 text-xs text-ink-2">{t('chat.searchingWeb')}</p>
            )}

            {failed && result && (
              <p className="px-3.5 py-3 text-xs text-error" role="alert" dir="auto">
                {result}
              </p>
            )}

            {!pending && !failed && hits.length === 0 && result && (
              <p className="px-3.5 py-3 text-xs text-ink-2" dir="auto">
                {result}
              </p>
            )}

            <ul className="divide-y divide-line">
              {hits.map((hit) => (
                <li key={hit.url}>
                  <a
                    href={hit.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    title={hit.snippet || hit.title}
                    className="flex items-center gap-3 px-3.5 py-2.5 text-sm transition
                      hover:bg-paper-3"
                  >
                    <img
                      src={faviconUrl(hit.domain)}
                      alt=""
                      width={16}
                      height={16}
                      className="size-4 shrink-0 rounded-sm"
                      loading="lazy"
                    />
                    <span className="min-w-0 flex-1 truncate text-ink" dir="auto">
                      {hit.title}
                    </span>
                    <span className="max-w-[40%] shrink-0 truncate text-xs text-ink-2">
                      {hit.domain}
                    </span>
                  </a>
                </li>
              ))}
            </ul>
          </div>

          {canScrollMore && (
            <>
              <div
                aria-hidden
                className="pointer-events-none absolute inset-x-0 bottom-0 h-10
                  rounded-b-2xl bg-gradient-to-t from-surface to-transparent"
              />
              <button
                type="button"
                aria-label={t('chat.searchScrollMore')}
                onClick={() => {
                  listRef.current?.scrollBy({ top: 120, behavior: 'smooth' })
                }}
                className="absolute bottom-2 left-1/2 flex size-8 -translate-x-1/2
                  items-center justify-center rounded-full border border-line
                  bg-surface text-ink-2 shadow-sm transition hover:text-ink"
              >
                <ChevronIcon width={16} height={16} className="rotate-90" />
              </button>
            </>
          )}
        </div>
      )}
    </div>
  )
}
