import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { ChevronIcon, SparkIcon, SpinnerIcon } from '@/components/Icons'
import { fileIdFromWriteResult, writeFilePayload, convertUploadPayload } from '@/components/chat/DocumentPreview'
import { Markdown } from '@/components/chat/Markdown'
import { FetchUrlResult } from '@/components/chat/FetchUrlResult'
import { WebSearchResults } from '@/components/chat/WebSearchResults'
import {
  pythonCodeFromArgs,
  skillDisplayName,
  toolDetail,
  toolDisplayName,
} from '@/lib/activityLabels'
import type { Block } from '@/types'

/** Successful tools that produced downloadable files. */
export function isWrittenFileBlock(
  block: Block,
): block is Extract<Block, { kind: 'tool' }> & { result: string } {
  if (block.kind !== 'tool' || block.failed) return false
  if (
    block.name !== 'write_file' &&
    block.name !== 'run_python' &&
    block.name !== 'convert_upload_to_docx'
  ) {
    return false
  }
  if (block.result === undefined) return false
  return Boolean(fileIdFromWriteResult(block.result))
}

/**
 * The reasoning block is the reason the UI does not look frozen: this model
 * thinks for minutes before its first visible token. Collapsed once finished,
 * because scratch work is not the answer. Claude-style: text row, no panel.
 */
function ReasoningBlock({ text, seconds, open }: Extract<Block, { kind: 'reasoning' }>) {
  const { t } = useTranslation()
  const [expanded, setExpanded] = useState(false)
  const streaming = open === true

  return (
    <div className="text-xs text-ink-2">
      <button
        type="button"
        onClick={() => setExpanded((value) => !value)}
        className="inline-flex items-center gap-1.5 py-0.5 text-start font-medium
          text-ink-2 transition hover:text-ink"
        aria-expanded={expanded}
      >
        {streaming ? (
          <SpinnerIcon width={12} height={12} />
        ) : (
          <ChevronIcon
            width={12}
            height={12}
            className={`transition-transform ${expanded ? 'rotate-90' : ''} rtl:-scale-x-100`}
          />
        )}
        {streaming ? t('chat.thinking') : t('chat.thoughtFor', { seconds })}
      </button>

      {streaming && !expanded ? (
        <div className="relative mt-1.5 flex max-h-[6.5rem] flex-col justify-end overflow-hidden ps-4">
          <div className="shrink-0">
            <Markdown text={text} compact />
          </div>
          <div
            className="pointer-events-none absolute inset-x-0 top-0 h-8
              bg-linear-to-b from-surface to-transparent"
          />
        </div>
      ) : null}

      {expanded ? (
        <div className="mt-1.5 max-h-72 overflow-y-auto ps-4 text-ink-2">
          <Markdown text={text} compact />
        </div>
      ) : null}
    </div>
  )
}

/** Guides are bookkeeping: quiet muted text, never a purple chip. */
function SkillChip({ name, loading }: Extract<Block, { kind: 'skill' }>) {
  const { t } = useTranslation()
  const label = skillDisplayName(name, t)
  return (
    <div className="inline-flex items-center gap-1.5 text-xs text-ink-2">
      {loading ? <SpinnerIcon width={12} height={12} /> : <SparkIcon width={12} height={12} />}
      <span>
        {loading ? t('chat.loadingSkill') : t('chat.usedSkill')}: {label}
      </span>
    </div>
  )
}

function peekStringArg(raw: string, keys: string[]): string {
  try {
    const parsed = JSON.parse(raw) as Record<string, unknown>
    for (const key of keys) {
      const value = parsed[key]
      if (typeof value === 'string' && value.trim()) return value.trim()
    }
  } catch {
    /* partial */
  }
  for (const key of keys) {
    const match = new RegExp(`"${key}"\\s*:\\s*"((?:\\\\.|[^"\\\\])*)"`).exec(raw)
    if (match) {
      try {
        return JSON.parse(`"${match[1]}"`) as string
      } catch {
        return match[1].replace(/\\"/g, '"')
      }
    }
  }
  return ''
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
  const detail = toolDetail(name, args, t)
  const pythonCode = name === 'run_python' ? pythonCodeFromArgs(args) : ''

  let summary = ''
  if (streaming) {
    if (detail) {
      summary = detail
    } else {
      const chars = argumentsChars ?? 0
      if (chars > 0) {
        summary =
          chars < 1024
            ? t('chat.writingArgsBytes', { size: chars })
            : t('chat.writingArgs', { size: (chars / 1024).toFixed(1) })
      }
    }
  } else if (detail) {
    summary = detail
  }

  const written =
    (name === 'write_file' ||
      name === 'run_python' ||
      name === 'convert_upload_to_docx') &&
    !pending &&
    !failed &&
    result !== undefined &&
    Boolean(fileIdFromWriteResult(result))
  const writeDraft = name === 'write_file' ? writeFilePayload(args) : null
  const convertDraft =
    name === 'convert_upload_to_docx' ? convertUploadPayload(args) : null
  const writeName =
    name === 'write_file'
      ? writeDraft?.name || peekStringArg(args, ['name']) || ''
      : name === 'convert_upload_to_docx'
        ? convertDraft?.name || convertDraft?.source || ''
        : ''

  if (name === 'web_search') {
    return (
      <WebSearchResults
        query={peekStringArg(args, ['query'])}
        result={result}
        pending={pending}
        failed={Boolean(failed)}
      />
    )
  }

  if (name === 'fetch_url') {
    return (
      <FetchUrlResult
        url={peekStringArg(args, ['url'])}
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
  if (
    (name === 'write_file' ||
      name === 'run_python' ||
      name === 'convert_upload_to_docx') &&
    awaitingApproval
  ) {
    return (
      <div className="inline-flex items-center gap-2 text-xs text-ink-2">
        <SpinnerIcon width={12} height={12} />
        <span dir="auto">
          {approvalPending
            ? t('chat.approvalSubmitting')
            : name === 'run_python'
              ? t('chat.approvalWaitingPython')
              : name === 'convert_upload_to_docx'
                ? t('chat.approvalWaitingConvert', {
                    name: writeName || 'document',
                  })
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
      <div className="inline-flex items-center gap-2 text-xs text-ink-2">
        <SpinnerIcon width={12} height={12} />
        <span dir="auto">{label}</span>
      </div>
    )
  }

  const canExpand =
    (!pending && result !== undefined) || (name === 'run_python' && pythonCode.length > 0)

  return (
    <div className="text-xs text-ink-2">
      <button
        type="button"
        onClick={() => setExpanded((value) => !value)}
        className="inline-flex max-w-full items-center gap-1.5 py-0.5 text-start
          transition hover:text-ink"
        aria-expanded={expanded}
        disabled={!canExpand}
      >
        {pending ? (
          <SpinnerIcon width={12} height={12} className="shrink-0" />
        ) : (
          <ChevronIcon
            width={12}
            height={12}
            className={`shrink-0 transition-transform
              ${expanded ? 'rotate-90' : ''} rtl:-scale-x-100`}
          />
        )}
        <span className={`font-medium ${failed ? 'text-error' : 'text-ink-2'}`}>
          {toolDisplayName(name, t)}
        </span>
        {summary ? (
          <span
            className={`truncate ${
              name === 'run_python'
                ? 'font-mono text-[12px] text-ink-3'
                : 'text-ink-3'
            }`}
            dir="auto"
          >
            {summary}
          </span>
        ) : null}
      </button>

      {expanded && name === 'run_python' && pythonCode ? (
        <pre
          className="mt-1.5 max-h-72 overflow-auto whitespace-pre-wrap ps-4 text-left font-mono
            text-[12px] leading-relaxed text-ink-3"
          dir="ltr"
        >
          {pythonCode}
        </pre>
      ) : null}

      {expanded && result !== undefined ? (
        <pre
          className="mt-1.5 max-h-72 overflow-auto whitespace-pre-wrap ps-4
            leading-relaxed text-ink-2"
          dir="auto"
        >
          {result}
        </pre>
      ) : null}
    </div>
  )
}

export function BlockView({
  block,
  compactText = false,
}: {
  block: Block
  /** Interim narration inside the activity trail. */
  compactText?: boolean
}) {
  switch (block.kind) {
    case 'text':
      return <AnswerBlock text={block.text} compact={compactText} />
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

/** Final prose — copy lives on the turn actions row, not here. */
function AnswerBlock({ text, compact = false }: { text: string; compact?: boolean }) {
  return (
    <div className={compact ? undefined : 'chat-answer'}>
      <Markdown text={text} compact={compact} />
    </div>
  )
}
