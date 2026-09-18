import { useEffect, useMemo, useRef, useState, type KeyboardEvent } from 'react'
import { useTranslation } from 'react-i18next'

import { useArtifact } from '@/components/chat/ArtifactContext'
import { DocxNativePreview } from '@/components/chat/DocxNativePreview'
import { Markdown } from '@/components/chat/Markdown'
import { PptxNativePreview } from '@/components/chat/PptxNativePreview'
import {
  parseSearchResultText,
  type ParsedSearchHit,
} from '@/components/chat/WebSearchResults'
import { XlsxNativePreview } from '@/components/chat/XlsxNativePreview'
import {
  CloseIcon,
  DownloadIcon,
  ExpandIcon,
  SpinnerIcon,
} from '@/components/Icons'
import { skillDisplayName, toolDetail, toolDisplayName } from '@/lib/activityLabels'
import { api } from '@/lib/api'
import type { Block, Turn } from '@/types'

const IMAGE_EXTS = new Set(['png', 'jpg', 'jpeg', 'gif', 'webp', 'bmp', 'svg'])

export function isImageFileName(name: string): boolean {
  const ext = name.includes('.') ? name.split('.').pop()!.toLowerCase() : ''
  return IMAGE_EXTS.has(ext)
}

function isDocxFileName(name: string): boolean {
  return name.toLowerCase().endsWith('.docx')
}

function isXlsxFileName(name: string): boolean {
  return name.toLowerCase().endsWith('.xlsx')
}

function isPptxFileName(name: string): boolean {
  return name.toLowerCase().endsWith('.pptx')
}

function extensionLabel(name: string): string {
  const ext = name.includes('.') ? name.split('.').pop()!.toLowerCase() : ''
  if (ext === 'docx' || ext === 'doc') return 'Word document'
  if (ext === 'xlsx' || ext === 'xls') return 'Spreadsheet'
  if (ext === 'pptx' || ext === 'ppt') return 'Presentation'
  if (ext === 'csv') return 'CSV'
  if (ext === 'pdf') return 'PDF'
  if (ext === 'md') return 'Markdown'
  if (ext === 'txt') return 'Text'
  if (IMAGE_EXTS.has(ext)) return ext.toUpperCase()
  return ext ? ext.toUpperCase() : 'File'
}


/** Shared type-badge colors for file cards, attachment chips, and Files page. */
export function fileBadgeClass(name: string): string {
  const lower = name.toLowerCase()
  if (lower.endsWith('.docx') || lower.endsWith('.doc')) {
    return 'bg-[#E8F0FE] text-[#1D4ED8] dark:bg-[#172554] dark:text-[#93C5FD]'
  }
  if (lower.endsWith('.xlsx') || lower.endsWith('.xls') || lower.endsWith('.csv')) {
    return 'bg-[#E6F4EA] text-[#1E7B34] dark:bg-[#14532D] dark:text-[#86EFAC]'
  }
  if (lower.endsWith('.pptx') || lower.endsWith('.ppt')) {
    return 'bg-[#FFF3E8] text-[#C2410C] dark:bg-[#431407] dark:text-[#FDBA74]'
  }
  if (lower.endsWith('.pdf')) {
    return 'bg-[#FDECEC] text-[#B42318] dark:bg-[#450A0A] dark:text-[#FCA5A5]'
  }
  if (isImageFileName(name)) {
    return 'bg-violet-tint text-violet-ink'
  }
  return 'bg-paper-3 text-ink-2'
}

function badgeShort(name: string): string {
  const lower = name.toLowerCase()
  if (lower.endsWith('.docx') || lower.endsWith('.doc')) return 'DOC'
  if (lower.endsWith('.xlsx') || lower.endsWith('.xls')) return 'XLS'
  if (lower.endsWith('.pptx') || lower.endsWith('.ppt')) return 'PPT'
  const kind = extensionLabel(name)
  if (kind.length <= 4) return kind
  return kind.slice(0, 3).toUpperCase()
}


/**
 * Compact file chip in the transcript — like Claude's artifact card.
 * Opens the side preview; does not dump the document body into the chat.
 */
export function DocumentFileCard({
  name,
  fileId,
  content,
  autoOpen = true,
}: {
  name: string
  fileId: string
  content?: string
  autoOpen?: boolean
}) {
  const { t } = useTranslation()
  const { artifact, openArtifact } = useArtifact()
  const active = artifact?.fileId === fileId
  const kind = extensionLabel(name)
  const isImage = isImageFileName(name)
  const thumbUrl = api.files.downloadUrl(fileId)

  useEffect(() => {
    if (!autoOpen) return
    openArtifact({ fileId, name, content })
  }, [autoOpen, fileId, name, content, openArtifact])

  return (
    <div
      className={`flex items-center gap-3.5 rounded-[14px] border bg-surface px-3.5 py-3
        transition ${
          active
            ? 'border-[1.5px] border-primary shadow-[0_0_0_4px_var(--color-violet-tint)]'
            : 'border-line hover:border-[#D6D1C7] dark:hover:border-line'
        }`}
    >
      <button
        type="button"
        onClick={() => openArtifact({ fileId, name, content })}
        className="flex min-w-0 flex-1 items-center gap-3.5 text-start"
      >
        {isImage ? (
          <img
            src={thumbUrl}
            alt=""
            className="size-10 shrink-0 rounded-[10px] object-cover ring-1 ring-line"
          />
        ) : (
          <div
            className={`flex size-10 shrink-0 items-center justify-center rounded-[10px]
              text-[11px] font-bold ${fileBadgeClass(name)}`}
          >
            {badgeShort(name)}
          </div>
        )}
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-semibold text-ink" dir="auto">
            {name}
          </p>
          <p className="text-xs text-ink-3">{kind}</p>
        </div>
      </button>
      <a
        href={api.files.downloadUrl(fileId)}
        download={name}
        aria-label={t('chat.downloadDocument')}
        className="inline-flex size-9 shrink-0 items-center justify-center rounded-[10px]
          border border-line text-ink-2 transition hover:bg-paper-3 hover:text-ink"
        onClick={(event) => event.stopPropagation()}
      >
        <DownloadIcon width={16} height={16} />
      </a>
    </div>
  )
}

export type TranscriptFile = {
  name: string
  fileId: string
  content?: string
  autoOpen?: boolean
}

function ImageFileTile({ name, fileId, content }: TranscriptFile) {
  const { t } = useTranslation()
  const { artifact, openArtifact } = useArtifact()
  const active = artifact?.fileId === fileId
  const thumbUrl = api.files.downloadUrl(fileId)

  return (
    <div className="min-w-0">
      <div
        className={`group relative aspect-[4/3] overflow-hidden rounded-xl border
          bg-paper-4 ${
            active
              ? 'border-[1.5px] border-primary shadow-[0_0_0_4px_var(--color-violet-tint)]'
              : 'border-line'
          }`}
      >
        <button
          type="button"
          onClick={() => openArtifact({ fileId, name, content })}
          className="absolute inset-0"
          aria-label={name}
        >
          <img src={thumbUrl} alt="" className="size-full object-contain" />
        </button>
        <a
          href={api.files.downloadUrl(fileId)}
          download={name}
          aria-label={t('chat.downloadDocument')}
          className="absolute end-1.5 top-1.5 z-10 hidden size-8 items-center justify-center
            rounded-lg border border-line bg-surface/95 text-ink-2 opacity-0 transition
            hover:bg-paper-3 hover:text-ink group-hover:flex group-hover:opacity-100
            group-focus-within:flex group-focus-within:opacity-100 focus-visible:flex
            focus-visible:opacity-100"
          onClick={(event) => event.stopPropagation()}
        >
          <DownloadIcon width={14} height={14} />
        </a>
      </div>
      <p
        className="mt-1.5 line-clamp-2 break-all text-xs text-ink-2"
        dir="auto"
        title={name}
      >
        {name}
      </p>
    </div>
  )
}

function CompactFileRow({ name, fileId, content }: TranscriptFile) {
  const { t } = useTranslation()
  const { artifact, openArtifact } = useArtifact()
  const active = artifact?.fileId === fileId

  return (
    <div
      className={`flex h-11 items-center gap-2.5 rounded-[12px] border bg-surface px-2.5
        transition ${
          active
            ? 'border-[1.5px] border-primary shadow-[0_0_0_4px_var(--color-violet-tint)]'
            : 'border-line'
        }`}
    >
      <button
        type="button"
        onClick={() => openArtifact({ fileId, name, content })}
        className="flex min-w-0 flex-1 items-center gap-2.5 text-start"
      >
        <div
          className={`flex size-7 shrink-0 items-center justify-center rounded-lg
            text-[10px] font-bold ${fileBadgeClass(name)}`}
        >
          {badgeShort(name)}
        </div>
        <span className="min-w-0 flex-1 truncate text-[13px] font-medium text-ink" dir="auto">
          {name}
        </span>
      </button>
      <a
        href={api.files.downloadUrl(fileId)}
        download={name}
        aria-label={t('chat.downloadDocument')}
        className="inline-flex size-8 shrink-0 items-center justify-center rounded-lg
          text-ink-2 transition hover:bg-paper-3 hover:text-ink"
        onClick={(event) => event.stopPropagation()}
      >
        <DownloadIcon width={15} height={15} />
      </a>
    </div>
  )
}

/**
 * 1–3 files: full cards. More than 3: image thumbnail grid + compact rows for the rest.
 */
export function DocumentFileList({ files }: { files: TranscriptFile[] }) {
  const { openArtifact } = useArtifact()
  const preferred = files.find((file) => file.autoOpen)

  useEffect(() => {
    if (!preferred || files.length <= 3) return
    openArtifact({
      fileId: preferred.fileId,
      name: preferred.name,
      content: preferred.content,
    })
  }, [preferred?.fileId, files.length, openArtifact]) // eslint-disable-line react-hooks/exhaustive-deps

  if (files.length <= 3) {
    return (
      <div className="space-y-2.5">
        {files.map((file, index) => (
          <DocumentFileCard
            key={`${file.fileId}-${index}`}
            name={file.name}
            fileId={file.fileId}
            content={file.content}
            autoOpen={file.autoOpen}
          />
        ))}
      </div>
    )
  }

  const images = files.filter((file) => isImageFileName(file.name))
  const others = files.filter((file) => !isImageFileName(file.name))

  return (
    <div className="space-y-2.5">
      {others.map((file, index) => (
        <CompactFileRow
          key={`o-${file.fileId}-${index}`}
          name={file.name}
          fileId={file.fileId}
          content={file.content}
        />
      ))}
      {images.length > 0 ? (
        <div className="grid grid-cols-3 gap-2.5">
          {images.map((file, index) => (
            <ImageFileTile
              key={`i-${file.fileId}-${index}`}
              name={file.name}
              fileId={file.fileId}
              content={file.content}
            />
          ))}
        </div>
      ) : null}
    </div>
  )
}

type WorkspaceTab = 'preview' | 'files' | 'sources' | 'steps'

type ConversationFile = {
  name: string
  fileId: string
  content?: string
}

function isProducedFileBlock(
  block: Block,
): block is Extract<Block, { kind: 'tool' }> & { result: string } {
  if (block.kind !== 'tool' || block.failed || block.result === undefined) return false
  if (
    block.name !== 'write_file' &&
    block.name !== 'run_python' &&
    block.name !== 'convert_upload_to_docx'
  ) {
    return false
  }
  return Boolean(fileIdFromWriteResult(block.result))
}

function collectConversationFiles(turns: Turn[]): ConversationFile[] {
  const found: ConversationFile[] = []
  const seen = new Set<string>()
  for (const turn of turns) {
    if (turn.role !== 'assistant') continue
    for (const block of turn.blocks) {
      if (!isProducedFileBlock(block)) continue
      const payload =
        block.name === 'write_file'
          ? writeFilePayload(block.args)
          : block.name === 'convert_upload_to_docx'
            ? convertUploadPayload(block.args)
            : null
      for (const file of filesFromToolResult(block.result)) {
        if (seen.has(file.id)) continue
        seen.add(file.id)
        found.push({
          fileId: file.id,
          name:
            (payload && 'name' in payload ? payload.name : undefined) ||
            (file.name !== 'document' ? file.name : undefined) ||
            'document',
          content: payload && 'content' in payload ? payload.content : undefined,
        })
      }
    }
  }
  return found
}

function collectConversationSources(turns: Turn[]): ParsedSearchHit[] {
  const found: ParsedSearchHit[] = []
  const seen = new Set<string>()
  for (const turn of turns) {
    if (turn.role !== 'assistant') continue
    for (const block of turn.blocks) {
      if (block.kind !== 'tool' || block.failed || !block.result) continue
      if (block.name === 'web_search') {
        for (const hit of parseSearchResultText(block.result)) {
          if (seen.has(hit.url)) continue
          seen.add(hit.url)
          found.push(hit)
        }
      } else if (block.name === 'fetch_url') {
        let url = ''
        try {
          const parsed = JSON.parse(block.args) as { url?: unknown }
          if (typeof parsed.url === 'string') url = parsed.url
        } catch {
          /* ignore */
        }
        if (!url || seen.has(url)) continue
        seen.add(url)
        let domain = url
        try {
          domain = new URL(url).hostname
        } catch {
          /* keep */
        }
        found.push({ title: domain, url, snippet: '', domain })
      }
    }
  }
  return found
}

function stepLabel(
  block: Block,
  t: (key: string, options?: Record<string, string | number>) => string,
): string {
  if (block.kind === 'reasoning') {
    return block.open ? t('chat.thinking') : t('chat.activityThought')
  }
  if (block.kind === 'skill') {
    return `${t('chat.usedSkill')}: ${skillDisplayName(block.name, t)}`
  }
  if (block.kind === 'tool') {
    if (block.name === 'web_search') return t('chat.webSearchDone')
    if (block.name === 'fetch_url') return t('chat.readPage')
    if (block.name === 'write_file') return t('chat.activityWroteFile')
    if (block.name === 'convert_upload_to_docx') return t('chat.activityConvertedDocx')
    if (block.name === 'run_python') return t('chat.activityRanPython')
    return toolDisplayName(block.name, t)
  }
  if (block.kind === 'error') return t('chat.activityError')
  return ''
}

function collectStepsForFile(turns: Turn[], fileId: string): Block[] {
  for (const turn of turns) {
    if (turn.role !== 'assistant') continue
    const produced = turn.blocks.some(
      (block) =>
        isProducedFileBlock(block) &&
        filesFromToolResult(block.result).some((file) => file.id === fileId),
    )
    if (!produced) continue
    return turn.blocks.filter(
      (block) => block.kind !== 'text' && !isProducedFileBlock(block),
    )
  }
  return []
}

/** Right-hand document pane — Quiet Workbench workspace with tabs. */
export function ArtifactPanel({ turns = [] }: { turns?: Turn[] }) {
  const { t, i18n } = useTranslation()
  const { artifact, openArtifact, closeArtifact } = useArtifact()
  const [body, setBody] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [expanded, setExpanded] = useState(false)
  const [tab, setTab] = useState<WorkspaceTab>('preview')
  const tablistRef = useRef<HTMLDivElement>(null)

  const files = useMemo(() => collectConversationFiles(turns), [turns])
  const sources = useMemo(() => collectConversationSources(turns), [turns])
  const steps = useMemo(
    () => (artifact ? collectStepsForFile(turns, artifact.fileId) : []),
    [turns, artifact],
  )

  const isImage = artifact ? isImageFileName(artifact.name) : false
  const isDocx = artifact ? isDocxFileName(artifact.name) : false
  const isXlsx = artifact ? isXlsxFileName(artifact.name) : false
  const isPptx = artifact ? isPptxFileName(artifact.name) : false

  const visibleTabs = useMemo(() => {
    const list: WorkspaceTab[] = ['preview', 'files']
    if (sources.length > 0) list.push('sources')
    list.push('steps')
    return list
  }, [sources.length])

  useEffect(() => {
    if (tab === 'sources' && sources.length === 0) setTab('preview')
  }, [tab, sources.length])

  useEffect(() => {
    if (!artifact) {
      setBody('')
      setError('')
      setLoading(false)
      return
    }
    if (
      isImageFileName(artifact.name) ||
      isDocxFileName(artifact.name) ||
      isXlsxFileName(artifact.name) ||
      isPptxFileName(artifact.name)
    ) {
      setBody('')
      setError('')
      setLoading(false)
      return
    }
    if (artifact.content?.trim()) {
      setBody(artifact.content)
      setError('')
      setLoading(false)
      return
    }
    let cancelled = false
    setLoading(true)
    setError('')
    api.files
      .preview(artifact.fileId)
      .then((preview) => {
        if (!cancelled) {
          setBody(preview.text)
          setLoading(false)
        }
      })
      .catch((problem: Error) => {
        if (!cancelled) {
          setError(problem.message)
          setLoading(false)
        }
      })
    return () => {
      cancelled = true
    }
  }, [artifact])

  const onTabKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    const rtl = i18n.language === 'ar' || document.documentElement.dir === 'rtl'
    const backward = rtl ? 'ArrowRight' : 'ArrowLeft'
    const forward = rtl ? 'ArrowLeft' : 'ArrowRight'
    if (event.key !== backward && event.key !== forward) return
    event.preventDefault()
    const index = visibleTabs.indexOf(tab)
    if (index < 0) return
    const delta = event.key === forward ? 1 : -1
    const next = visibleTabs[(index + delta + visibleTabs.length) % visibleTabs.length]
    setTab(next)
    tablistRef.current
      ?.querySelector<HTMLButtonElement>(`[data-tab="${next}"]`)
      ?.focus()
  }

  if (!artifact) return null

  const tabClass = (id: WorkspaceTab) =>
    `inline-flex h-8 shrink-0 items-center gap-1 rounded-lg px-3 text-[13px] transition ${
      tab === id
        ? 'bg-paper-3 font-semibold text-ink'
        : 'text-ink-2 hover:bg-paper-3/70 hover:text-ink'
    }`

  return (
    <aside
      className={`flex h-full min-h-0 w-[460px] max-w-full shrink-0 flex-col border-s
        border-line bg-surface animate-chat-in
        ${
          expanded
            ? 'absolute inset-0 z-20 w-full max-w-none'
            : `absolute inset-0 z-20 w-full
              md:static md:inset-auto md:w-[min(100%,460px)]`
        }`}
    >
      <header className="flex h-[60px] shrink-0 items-center gap-2 border-b border-line px-3">
        <div
          ref={tablistRef}
          role="tablist"
          aria-label={t('workspace.preview')}
          className="flex min-w-0 flex-1 items-center gap-1 overflow-x-auto"
          onKeyDown={onTabKeyDown}
        >
          <button
            type="button"
            role="tab"
            data-tab="preview"
            aria-selected={tab === 'preview'}
            className={tabClass('preview')}
            onClick={() => setTab('preview')}
          >
            {t('workspace.preview')}
          </button>
          <button
            type="button"
            role="tab"
            data-tab="files"
            aria-selected={tab === 'files'}
            className={tabClass('files')}
            onClick={() => setTab('files')}
          >
            {t('workspace.files')}
            <span className="text-ink-3">{files.length}</span>
          </button>
          {sources.length > 0 ? (
            <button
              type="button"
              role="tab"
              data-tab="sources"
              aria-selected={tab === 'sources'}
              className={tabClass('sources')}
              onClick={() => setTab('sources')}
            >
              {t('workspace.sources')}
              <span className="text-ink-3">{sources.length}</span>
            </button>
          ) : null}
          <button
            type="button"
            role="tab"
            data-tab="steps"
            aria-selected={tab === 'steps'}
            className={tabClass('steps')}
            onClick={() => setTab('steps')}
          >
            {t('workspace.steps')}
          </button>
        </div>
        <button
          type="button"
          aria-label={expanded ? t('chat.shrinkPreview') : t('workspace.fullscreen')}
          onClick={() => setExpanded((value) => !value)}
          className="inline-flex size-[34px] items-center justify-center rounded-[10px]
            text-ink-2 transition hover:bg-paper-3 hover:text-ink"
        >
          <ExpandIcon width={16} height={16} />
        </button>
        <button
          type="button"
          aria-label={t('workspace.close')}
          onClick={closeArtifact}
          className="inline-flex size-[34px] items-center justify-center rounded-[10px]
            text-ink-2 transition hover:bg-paper-3 hover:text-ink"
        >
          <CloseIcon width={16} height={16} />
        </button>
      </header>

      {tab === 'preview' ? (
        <div className="flex shrink-0 items-center gap-2.5 border-b border-line-soft px-4 py-2.5">
          <div
            className={`flex size-7 shrink-0 items-center justify-center rounded-[8px]
              text-[10px] font-bold ${fileBadgeClass(artifact.name)}`}
          >
            {badgeShort(artifact.name)}
          </div>
          <p className="min-w-0 flex-1 truncate text-[13px] font-semibold text-ink" dir="auto">
            {artifact.name}
          </p>
          <a
            href={api.files.downloadUrl(artifact.fileId)}
            download={artifact.name}
            className="inline-flex h-8 items-center gap-1.5 rounded-[10px] bg-primary px-3
              text-xs font-semibold text-white transition hover:bg-primary-600"
          >
            <DownloadIcon width={14} height={14} />
            {t('chat.downloadDocument')}
          </a>
        </div>
      ) : null}

      <div className="min-h-0 flex-1 overflow-auto bg-paper-4 p-6">
        {tab === 'preview' && isImage ? (
          <div className="flex items-start justify-center">
            <img
              src={api.files.downloadUrl(artifact.fileId)}
              alt={artifact.name}
              className="h-auto max-w-full rounded bg-white
                shadow-[0_1px_2px_rgb(28_26_36/0.06),0_8px_24px_-16px_rgb(28_26_36/0.25)]"
            />
          </div>
        ) : null}
        {tab === 'preview' && isDocx ? (
          <div className="min-h-min min-w-0">
            <DocxNativePreview fileId={artifact.fileId} />
          </div>
        ) : null}
        {tab === 'preview' && isXlsx ? (
          <div className="flex min-h-full min-w-0 flex-col">
            <XlsxNativePreview fileId={artifact.fileId} />
          </div>
        ) : null}
        {tab === 'preview' && isPptx ? (
          <div className="min-h-min min-w-0">
            <PptxNativePreview fileId={artifact.fileId} />
          </div>
        ) : null}
        {tab === 'preview' && !isImage && !isDocx && !isXlsx && !isPptx ? (
          <div
            className="mx-auto min-h-full max-w-2xl rounded bg-white px-8 py-10
              shadow-[0_1px_2px_rgb(28_26_36/0.06),0_8px_24px_-16px_rgb(28_26_36/0.25)]
              sm:px-12 sm:py-14"
          >
            {loading && (
              <div className="flex items-center gap-2 text-sm text-ink-2">
                <SpinnerIcon width={16} height={16} />
                {t('common.loading')}
              </div>
            )}
            {error && (
              <p className="text-sm text-error" role="alert">
                {error}
              </p>
            )}
            {!loading && !error && body && <Markdown text={body} />}
          </div>
        ) : null}

        {tab === 'files' ? (
          <ul className="space-y-1.5">
            {files.length === 0 ? (
              <li className="text-sm text-ink-3">{t('nav.noResults')}</li>
            ) : (
              files.map((file) => {
                const active = file.fileId === artifact.fileId
                return (
                  <li key={file.fileId}>
                    <button
                      type="button"
                      onClick={() => {
                        openArtifact({
                          fileId: file.fileId,
                          name: file.name,
                          content: file.content,
                        })
                        setTab('preview')
                      }}
                      className={`flex w-full items-center gap-2.5 rounded-[12px] border px-2.5
                        py-2 text-start transition ${
                          active
                            ? 'border-[1.5px] border-primary bg-surface shadow-[0_0_0_4px_var(--color-violet-tint)]'
                            : 'border-line bg-surface hover:bg-paper-2'
                        }`}
                    >
                      <span
                        className={`flex size-7 shrink-0 items-center justify-center rounded-lg
                          text-[10px] font-bold ${fileBadgeClass(file.name)}`}
                      >
                        {badgeShort(file.name)}
                      </span>
                      <span
                        className="min-w-0 flex-1 truncate text-[13px] font-medium text-ink"
                        dir="auto"
                        title={file.name}
                      >
                        {file.name}
                      </span>
                    </button>
                  </li>
                )
              })
            )}
          </ul>
        ) : null}

        {tab === 'sources' ? (
          <ul className="space-y-2">
            {sources.map((hit) => (
              <li key={hit.url}>
                <a
                  href={hit.url}
                  target="_blank"
                  rel="noreferrer"
                  className="block rounded-[12px] border border-line bg-surface px-3 py-2.5
                    transition hover:bg-paper-2"
                >
                  <p className="truncate text-[13px] font-semibold text-ink" dir="auto">
                    {hit.title}
                  </p>
                  <p className="mt-0.5 truncate text-xs text-ink-3" dir="ltr">
                    {hit.domain}
                  </p>
                </a>
              </li>
            ))}
          </ul>
        ) : null}

        {tab === 'steps' ? (
          <div className="space-y-2 rounded-2xl border border-line bg-surface p-3">
            {steps.length === 0 ? (
              <p className="text-sm text-ink-3">{t('nav.noResults')}</p>
            ) : (
              steps.map((block, index) => {
                const label = stepLabel(block, t)
                if (!label) return null
                const detail =
                  block.kind === 'tool' ? toolDetail(block.name, block.args, t) : null
                return (
                  <div key={`step-${index}`} className="text-[13px] text-ink-2">
                    <p>{label}</p>
                    {detail ? (
                      <p
                        className={`mt-0.5 truncate ${
                          block.kind === 'tool' && block.name === 'run_python'
                            ? 'font-mono text-[12px] text-ink-3'
                            : 'text-ink-3'
                        }`}
                        dir="auto"
                      >
                        {detail}
                      </p>
                    ) : null}
                  </div>
                )
              })
            )}
          </div>
        ) : null}
      </div>
    </aside>
  )
}

/** Pull the file id out of a write_file tool result line. */
export function fileIdFromWriteResult(result: string): string | null {
  const match = result.match(/\/api\/files\/([0-9a-f-]{36})\/download/i)
  return match?.[1] ?? null
}

/** All downloadable files mentioned in a tool result (write_file or run_python). */
export function filesFromToolResult(
  result: string,
): { id: string; name: string }[] {
  const found: { id: string; name: string }[] = []
  const seen = new Set<string>()
  const lineRe =
    /(?:^|\n)\s*[-*]?\s*(.+?)\s+\(\d+\s+bytes\)\s+[—-]\s+\/api\/files\/([0-9a-f-]{36})\/download/gi
  for (const match of result.matchAll(lineRe)) {
    const name = match[1].trim()
    const id = match[2]
    if (seen.has(id)) continue
    seen.add(id)
    found.push({ id, name: name || 'document' })
  }
  if (found.length === 0) {
    const id = fileIdFromWriteResult(result)
    if (id) found.push({ id, name: 'document' })
  }
  return found
}

export function writeFilePayload(args: string): { name: string; content: string } | null {
  try {
    const parsed = JSON.parse(args) as { name?: unknown; content?: unknown }
    if (typeof parsed.name !== 'string') return null
    return {
      name: parsed.name,
      content: typeof parsed.content === 'string' ? parsed.content : '',
    }
  } catch {
    return null
  }
}

/** Args for convert_upload_to_docx — source upload and optional output name. */
export function convertUploadPayload(
  args: string,
): { source: string; name: string } | null {
  try {
    const parsed = JSON.parse(args) as { source?: unknown; name?: unknown }
    if (typeof parsed.source !== 'string' || !parsed.source.trim()) return null
    const source = parsed.source.trim()
    const explicit =
      typeof parsed.name === 'string' && parsed.name.trim() ? parsed.name.trim() : ''
    const name = explicit || source.replace(/\.[^.]+$/, '') + '.docx'
    return { source, name }
  } catch {
    const sourceMatch = /"source"\s*:\s*"((?:\\.|[^"\\])*)"/.exec(args)
    if (!sourceMatch) return null
    const source = sourceMatch[1].replace(/\\"/g, '"')
    const nameMatch = /"name"\s*:\s*"((?:\\.|[^"\\])*)"/.exec(args)
    const explicit = nameMatch ? nameMatch[1].replace(/\\"/g, '"') : ''
    return {
      source,
      name: explicit || source.replace(/\.[^.]+$/, '') + '.docx',
    }
  }
}

/** @deprecated Use DocumentFileCard — kept name for older imports. */
export const DocumentPreview = DocumentFileCard
