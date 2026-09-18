import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { ChevronIcon, SpinnerIcon } from '@/components/Icons'

function domainOf(url: string): string {
  try {
    return new URL(url).hostname
  } catch {
    return url
  }
}

function faviconUrl(domain: string): string {
  return `https://www.google.com/s2/favicons?domain=${encodeURIComponent(domain)}&sz=32`
}

/** First useful line of the fetched page — good enough as a title stand-in. */
function titleFromBody(body: string): string {
  for (const line of body.split('\n')) {
    const trimmed = line.trim()
    if (trimmed.length < 3) continue
    if (trimmed.startsWith('[truncated')) continue
    return trimmed.length > 120 ? `${trimmed.slice(0, 117)}…` : trimmed
  }
  return ''
}

function previewLines(body: string, limit = 8): string {
  return body
    .split('\n')
    .map((line) => line.trimEnd())
    .filter((line, index, all) => line.trim() || (index > 0 && all[index - 1].trim()))
    .slice(0, limit)
    .join('\n')
}

/**
 * One source row for fetch_url. Finished reads stay a single line; expand for
 * title card + short preview so the answer keeps visual priority.
 */
export function FetchUrlResult({
  url,
  result,
  pending,
  failed,
}: {
  url: string
  result?: string
  pending: boolean
  failed: boolean
}) {
  const { t } = useTranslation()
  const [open, setOpen] = useState(false)
  const domain = url ? domainOf(url) : ''
  const title =
    result && !failed ? titleFromBody(result) || domain || url : domain || url || '…'
  const preview = result && !failed ? previewLines(result) : ''
  const hasDetails = Boolean(preview) || Boolean(url && !pending && !failed)
  const showPanel = pending || failed || open

  return (
    <div className="space-y-1.5">
      <button
        type="button"
        onClick={() => hasDetails && setOpen((value) => !value)}
        disabled={!hasDetails}
        className="flex w-full items-center gap-1.5 text-start text-xs text-ink-2
          disabled:cursor-default"
        aria-expanded={hasDetails ? open : undefined}
      >
        <span>
          {pending ? t('chat.readingPage') : t('chat.readPage')}{' '}
          <span className="font-medium text-ink-3" dir="auto">
            {domain || url || '…'}
          </span>
        </span>
        {pending ? (
          <SpinnerIcon width={12} height={12} className="shrink-0" />
        ) : hasDetails ? (
          <ChevronIcon
            width={13}
            height={13}
            className={`shrink-0 transition-transform ${open ? 'rotate-90' : ''}
              rtl:-scale-x-100`}
          />
        ) : null}
      </button>

      {showPanel ? (
        <div
          className={`overflow-hidden rounded-xl border border-line bg-surface
            ${failed ? 'border-error-200 bg-error-50' : ''}`}
        >
          {pending && (
            <p className="px-3 py-2.5 text-xs text-ink-2">{t('chat.readingPage')}</p>
          )}

          {failed && result && (
            <p className="px-3 py-2.5 text-xs text-error" role="alert" dir="auto">
              {result}
            </p>
          )}

          {!pending && !failed && url && (
            <a
              href={url}
              target="_blank"
              rel="noopener noreferrer"
              className="flex items-center gap-3 px-3 py-2 text-sm transition
                hover:bg-paper-3"
            >
              {domain && (
                <img
                  src={faviconUrl(domain)}
                  alt=""
                  width={16}
                  height={16}
                  className="size-4 shrink-0 rounded-sm"
                  loading="lazy"
                />
              )}
              <span className="min-w-0 flex-1 truncate text-ink" dir="auto">
                {title}
              </span>
              {domain && (
                <span className="max-w-[40%] shrink-0 truncate text-xs text-ink-2">
                  {domain}
                </span>
              )}
            </a>
          )}

          {open && preview && (
            <pre
              className="max-h-40 overflow-auto whitespace-pre-wrap border-t
                border-line px-3 py-2 text-xs leading-relaxed text-ink-2"
              dir="auto"
            >
              {preview}
              {result && result.split('\n').length > 8 ? '\n…' : ''}
            </pre>
          )}
        </div>
      ) : null}
    </div>
  )
}
