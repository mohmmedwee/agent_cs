import type { ReactNode } from 'react'
import { useTranslation } from 'react-i18next'

export type DiffSegment = {
  kind: 'equal' | 'delete' | 'insert'
  text: string
}

export type ApprovalChange = {
  op: string
  block_id: string
  before: string
  after: string
  before_segments?: DiffSegment[]
  after_segments?: DiffSegment[]
  notes?: string[]
}

/** Server-built card — Composer only renders; never recomputes diffs. */
export type ApprovalCard = {
  file_name: string
  from_version: number
  to_version: number
  change_count: number
  changes: ApprovalChange[]
  omitted_count: number
  notes?: string[]
}

function SegmentLine({
  segments,
  plain,
}: {
  segments?: DiffSegment[]
  plain: string
}) {
  if (!segments?.length) {
    return (
      <span className="whitespace-pre-wrap break-words" dir="auto">
        {plain}
      </span>
    )
  }
  return (
    <span className="whitespace-pre-wrap break-words" dir="auto">
      {segments.map((seg, i) => {
        const key = `${seg.kind}-${i}-${seg.text.slice(0, 12)}`
        if (seg.kind === 'delete') {
          return (
            <mark
              key={key}
              className="rounded-sm bg-error-50 text-error line-through decoration-error/60"
            >
              {seg.text}
            </mark>
          )
        }
        if (seg.kind === 'insert') {
          return (
            <mark key={key} className="rounded-sm bg-paper-2 text-ink underline decoration-primary/50">
              {seg.text}
            </mark>
          )
        }
        return <span key={key}>{seg.text}</span>
      })}
    </span>
  )
}

export function ApprovalDiffCard({ card }: { card: ApprovalCard }) {
  const { t } = useTranslation()
  const header = t('chat.approvalEditHeader', {
    name: card.file_name,
    from: card.from_version,
    to: card.to_version,
    count: card.change_count,
  })

  return (
    <div className="mt-2 space-y-2">
      <p className="text-xs font-medium text-ink" dir="auto">
        {header}
      </p>
      {card.notes?.length ? (
        <p className="text-[11px] text-ink-3" dir="auto">
          {card.notes.join(' · ')}
        </p>
      ) : null}
      <ul className="max-h-64 space-y-2 overflow-y-auto pe-1">
        {card.changes.map((change) => (
          <li
            key={`${change.block_id}-${change.op}-${change.before.slice(0, 24)}`}
            className="rounded-xl border border-line bg-paper-3 px-3 py-2 text-[12px]"
          >
            <p className="font-mono text-[10px] uppercase tracking-wide text-ink-3">
              {change.op} · {change.block_id}
            </p>
            {change.op === 'insert' ? (
              <p className="mt-1 text-ink" dir="auto">
                <span className="text-ink-3">+</span>{' '}
                <SegmentLine plain={change.after} />
              </p>
            ) : change.op === 'delete' ? (
              <p className="mt-1 text-ink" dir="auto">
                <span className="text-ink-3">−</span>{' '}
                <SegmentLine plain={change.before} />
              </p>
            ) : (
              <div className="mt-1 space-y-1">
                <p className="text-ink">
                  <span className="me-1 text-ink-3">−</span>
                  <SegmentLine
                    segments={change.before_segments}
                    plain={change.before}
                  />
                </p>
                <p className="text-ink">
                  <span className="me-1 text-ink-3">+</span>
                  <SegmentLine
                    segments={change.after_segments}
                    plain={change.after}
                  />
                </p>
              </div>
            )}
            {change.notes?.length ? (
              <p className="mt-1 text-[10px] text-ink-3" dir="auto">
                {change.notes.join(' · ')}
              </p>
            ) : null}
          </li>
        ))}
      </ul>
      {card.omitted_count > 0 ? (
        <p className="text-[11px] text-ink-3">
          {t('chat.approvalEditMore', { count: card.omitted_count })}
        </p>
      ) : null}
    </div>
  )
}

/** Escape check helper for tests — card text must never be interpreted as HTML. */
export function renderPlain(text: string): ReactNode {
  return text
}
