import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { CheckIcon, ChevronIcon, CopyIcon, SparkIcon, SpinnerIcon } from '@/components/Icons'
import { fileIdFromWriteResult, writeFilePayload } from '@/components/chat/DocumentPreview'
import { Markdown } from '@/components/chat/Markdown'
import { FetchUrlResult } from '@/components/chat/FetchUrlResult'
import { WebSearchResults } from '@/components/chat/WebSearchResults'
import { skillDisplayName, toolDisplayName } from '@/lib/activityLabels'
import type { Block } from '@/types'

/** Successful write_file tools — shown after the answer, not mid-stream. */
export function isWrittenFileBlock(
  block: Block,
): block is Extract<Block, { kind: 'tool' }> & { result: string } {
  if (block.kind !== 'tool' || block.name !== 'write_file' || block.failed) return false
  if (block.result === undefined) return false
  return Boolean(fileIdFromWriteResult(block.result))
}

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

/** Guides are bookkeeping: a chip, never the skill body. */
function SkillChip({ name, loading }: Extract<Block, { kind: 'skill' }>) {
  const { t } = useTranslation()
  const label = skillDisplayName(name, t)
  return (
    <div
      className="inline-flex items-center gap-1.5 rounded-full bg-primary-25 px-3 py-1
        text-xs font-medium text-primary"
    >
      {loading ? <SpinnerIcon width={12} height={12} /> : <SparkIcon width={12} height={12} />}
      <span>
        {loading ? t('chat.loadingSkill') : t('chat.usedSkill')}: {label}
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
  awaitingApproval,
  approvalPending,
}: Extract<Block, { kind: 'tool' }>) {
  const { t } = useTranslation()
  const [expanded, setExpanded] = useState(false)
  const pending = result === undefined

  // Show the useful argument inline — the query, the URL, the file name —
  // rather than raw JSON, which is noise at a glance.
  let summary = ''
  const peekArg = (raw: string): string => {
    try {
      const parsed = JSON.parse(raw) as Record<string, unknown>
      return String(parsed.query ?? parsed.url ?? parsed.name ?? parsed.expression ?? '')
    } catch {
      const match = /"(?:query|url|name|expression)"\s*:\s*"((?:\\.|[^"\\])*)"/.exec(raw)
      return match ? match[1].replace(/\\"/g, '"') : ''
    }
  }
  /** Partial write_file JSON often has `"name":"…"` before `content` finishes. */
  const peekFileName = (raw: string): string => {
    const fromPayload = writeFilePayload(raw)?.name
    if (fromPayload) return fromPayload
    try {
      const parsed = JSON.parse(raw) as Record<string, unknown>
      const name = parsed.name
      return typeof name === 'string' ? name : ''
    } catch {
      const match = /"name"\s*:\s*"((?:\\.|[^"\\])*)"/.exec(raw)
      return match ? match[1].replace(/\\"/g, '"') : ''
    }
  }
  if (streaming) {
    summary = peekArg(args)
    if (!summary) {
      const chars = argumentsChars ?? 0
      summary =
        chars < 1024
          ? t('chat.writingArgsBytes', { size: chars })
          : t('chat.writingArgs', { size: (chars / 1024).toFixed(1) })
    }
  } else {
    summary = peekArg(args) || args.slice(0, 80)
  }

  const written =
    name === 'write_file' &&
    !pending &&
    !failed &&
    result !== undefined &&
    Boolean(fileIdFromWriteResult(result))
  const writeDraft = name === 'write_file' ? writeFilePayload(args) : null
  const writeName =
    name === 'write_file' ? writeDraft?.name || peekFileName(args) || '' : ''

  if (name === 'web_search') {
    return (
      <WebSearchResults
        query={summary}
        result={result}
        pending={pending}
        failed={Boolean(failed)}
      />
    )
  }

  if (name === 'fetch_url') {
    return (
      <FetchUrlResult
        url={summary}
        result={result}
        pending={pending}
        failed={Boolean(failed)}
      />
    )
  }

  // Successful writes are rendered after the answer text (see ChatPage).
  if (written) {
    return null
  }

  // Allow / Deny lives in the composer; chat only shows a waiting hint.
  if (name === 'write_file' && awaitingApproval) {
    return (
      <div
        className="inline-flex items-center gap-2 rounded-full border border-primary-100
          bg-primary-25/80 px-3 py-1.5 text-xs font-medium text-primary"
      >
        <SpinnerIcon width={12} height={12} />
        <span dir="auto">
          {approvalPending
            ? t('chat.approvalSubmitting')
            : t('chat.approvalWaiting', {
                name: writeName || 'document',
              })}
        </span>
      </div>
    )
  }

  if (name === 'write_file' && pending) {
    const chars = argumentsChars ?? 0
    let label: string
    if (streaming) {
      if (writeName && chars > 0) {
        label =
          chars < 1024
            ? t('chat.writingFileProgressBytes', { name: writeName, size: chars })
            : t('chat.writingFileProgress', {
                name: writeName,
                size: (chars / 1024).toFixed(1),
              })
      } else if (writeName) {
        label = t('chat.writingFile', { name: writeName })
      } else if (chars > 0) {
        label =
          chars < 1024
            ? t('chat.writingArgsBytes', { size: chars })
            : t('chat.writingArgs', { size: (chars / 1024).toFixed(1) })
      } else {
        label = t('chat.writingFileStarting')
      }
    } else {
      label = t('chat.writingFile', { name: writeName || 'document' })
    }

    return (
      <div
        className="inline-flex items-center gap-2 rounded-full border border-secondary-200
          bg-secondary-25 px-3 py-1.5 text-xs font-medium text-secondary"
      >
        <SpinnerIcon width={12} height={12} />
        <span dir="auto">{label}</span>
      </div>
    )
  }

  return (
    <div className="space-y-2.5">
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
          <span className={`font-medium ${failed ? 'text-error' : 'text-primary'}`}>
            {toolDisplayName(name, t)}
          </span>
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
    </div>
  )
}

export function BlockView({ block }: { block: Block }) {
  switch (block.kind) {
    case 'text':
      return <AnswerBlock text={block.text} />
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

/** Final prose: tinted surface + copy on hover so it reads as the answer. */
function AnswerBlock({ text }: { text: string }) {
  const { t } = useTranslation()
  const [copied, setCopied] = useState(false)

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(text)
      setCopied(true)
      window.setTimeout(() => setCopied(false), 1600)
    } catch {
      /* clipboard can fail in insecure contexts */
    }
  }

  return (
    <div className="chat-answer group relative">
      <button
        type="button"
        onClick={() => void copy()}
        aria-label={copied ? t('chat.copied') : t('chat.copy')}
        className="absolute end-2 top-2 rounded-lg border border-secondary-200
          bg-surface p-1.5 text-secondary opacity-0 shadow-sm transition
          hover:text-dark group-hover:opacity-100 focus-visible:opacity-100"
      >
        {copied ? (
          <CheckIcon width={14} height={14} className="text-success" />
        ) : (
          <CopyIcon width={14} height={14} />
        )}
      </button>
      <Markdown text={text} />
    </div>
  )
}
