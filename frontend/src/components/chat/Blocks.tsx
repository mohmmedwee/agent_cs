import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { ChevronIcon, SparkIcon, SpinnerIcon } from '@/components/Icons'
import { Markdown } from '@/components/chat/Markdown'
import type { Block } from '@/types'

/**
 * The reasoning block is the reason the UI does not look frozen: this model
 * thinks for minutes before its first visible token. Collapsed once finished,
 * because scratch work is not the answer.
 */
function ReasoningBlock({ text, seconds, open }: Extract<Block, { kind: 'reasoning' }>) {
  const { t } = useTranslation()
  const [expanded, setExpanded] = useState(false)
  const streaming = open === true

  return (
    <div className="rounded-xl border border-secondary-200 bg-secondary-25">
      <button
        type="button"
        onClick={() => setExpanded((value) => !value)}
        className="flex w-full items-center gap-2 px-3 py-2 text-start text-xs
          font-medium text-secondary transition hover:text-dark"
        aria-expanded={expanded}
      >
        {streaming ? (
          <SpinnerIcon width={13} height={13} />
        ) : (
          <ChevronIcon
            width={13}
            height={13}
            className={`transition-transform ${expanded ? 'rotate-90' : ''} rtl:-scale-x-100`}
          />
        )}
        {streaming ? t('chat.thinking') : t('chat.thoughtFor', { seconds })}
      </button>

      {expanded && (
        <div className="max-h-72 overflow-y-auto border-t border-secondary-200 px-3 py-2.5">
          <Markdown text={text} compact />
        </div>
      )}
    </div>
  )
}

/** Skills are bookkeeping: a chip, never the skill body. */
function SkillChip({ name, loading }: Extract<Block, { kind: 'skill' }>) {
  const { t } = useTranslation()
  return (
    <div
      className="inline-flex items-center gap-1.5 rounded-full bg-primary-25 px-3 py-1
        text-xs font-medium text-primary"
    >
      {loading ? <SpinnerIcon width={12} height={12} /> : <SparkIcon width={12} height={12} />}
      <span>
        {loading ? t('chat.loadingSkill') : t('chat.usedSkill')}: {name}
      </span>
    </div>
  )
}

function ToolBlock({
  name,
  args,
  result,
  failed,
  streaming,
  argumentsChars,
}: Extract<Block, { kind: 'tool' }>) {
  const { t } = useTranslation()
  const [expanded, setExpanded] = useState(false)
  const pending = result === undefined

  // Show the useful argument inline — the query, the URL, the file name —
  // rather than raw JSON, which is noise at a glance.
  let summary = ''
  if (streaming) {
    const chars = argumentsChars ?? 0
    summary =
      chars < 1024
        ? t('chat.writingArgsBytes', { size: chars })
        : t('chat.writingArgs', { size: (chars / 1024).toFixed(1) })
  } else {
    try {
      const parsed = JSON.parse(args) as Record<string, unknown>
      summary = String(parsed.query ?? parsed.url ?? parsed.name ?? parsed.expression ?? '')
    } catch {
      summary = args.slice(0, 80)
    }
  }

  return (
    <div
      className={`rounded-xl border text-xs ${
        failed ? 'border-error-200 bg-error-50' : 'border-secondary-200 bg-secondary-25'
      }`}
    >
      <button
        type="button"
        onClick={() => setExpanded((value) => !value)}
        className="flex w-full items-center gap-2 px-3 py-2 text-start"
        aria-expanded={expanded}
        disabled={pending}
      >
        {pending ? (
          <SpinnerIcon width={13} height={13} className="text-secondary" />
        ) : (
          <ChevronIcon
            width={13}
            height={13}
            className={`shrink-0 text-secondary transition-transform
              ${expanded ? 'rotate-90' : ''} rtl:-scale-x-100`}
          />
        )}
        <code className={`font-mono font-medium ${failed ? 'text-error' : 'text-primary'}`}>
          {name}
        </code>
        {summary && (
          <span className="truncate text-secondary" dir="auto">
            {summary}
          </span>
        )}
      </button>

      {expanded && result !== undefined && (
        <pre
          className="max-h-72 overflow-auto whitespace-pre-wrap border-t
            border-secondary-200 px-3 py-2.5 leading-relaxed text-secondary"
          dir="auto"
        >
          {result}
        </pre>
      )}
    </div>
  )
}

export function BlockView({ block }: { block: Block }) {
  switch (block.kind) {
    case 'text':
      // The answer gets a surface of its own. Bare prose beside the user's
      // bubble read as unstyled, and left the reply indistinguishable from the
      // tool and reasoning cards around it.
      return (
        <div className="card px-4 py-3">
          <Markdown text={block.text} />
        </div>
      )
    case 'reasoning':
      return <ReasoningBlock {...block} />
    case 'skill':
      return <SkillChip {...block} />
    case 'tool':
      return <ToolBlock {...block} />
    case 'error':
      return (
        <p
          role="alert"
          className="rounded-xl bg-error-50 px-3.5 py-2.5 text-sm text-error"
          dir="auto"
        >
          {block.message}
        </p>
      )
  }
}
