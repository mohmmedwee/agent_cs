import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'

import { useArtifact } from '@/components/chat/ArtifactContext'
import { Markdown } from '@/components/chat/Markdown'
import {
  CloseIcon,
  DownloadIcon,
  ExpandIcon,
  FileIcon,
  SpinnerIcon,
} from '@/components/Icons'
import { api } from '@/lib/api'

function extensionLabel(name: string): string {
  const ext = name.includes('.') ? name.split('.').pop()!.toUpperCase() : ''
  if (ext === 'DOCX') return 'DOCX'
  if (ext === 'MD') return 'Markdown'
  if (ext === 'TXT') return 'Text'
  return ext || 'File'
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

  useEffect(() => {
    if (!autoOpen) return
    openArtifact({ fileId, name, content })
  }, [autoOpen, fileId, name, content, openArtifact])

  return (
    <div
      className={`flex items-center gap-3 rounded-2xl border px-3.5 py-3 transition
        ${
          active
            ? 'border-primary-300 bg-primary-25 shadow-sm'
            : 'border-secondary-200 bg-surface hover:border-primary-200'
        }`}
    >
      <button
        type="button"
        onClick={() => openArtifact({ fileId, name, content })}
        className="flex min-w-0 flex-1 items-center gap-3 text-start"
      >
        <div
          className="flex size-10 shrink-0 items-center justify-center rounded-xl
            bg-primary-50 text-primary"
        >
          <FileIcon width={20} height={20} />
        </div>
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-semibold text-dark" dir="auto">
            {name.replace(/\.[^.]+$/, '') || name}
          </p>
          <p className="text-xs text-secondary">
            {t('chat.documentKind', { kind })}
          </p>
        </div>
      </button>
      <a
        href={api.files.downloadUrl(fileId)}
        download={name}
        className="btn-primary !rounded-xl !px-3 !py-2 text-xs"
        onClick={(event) => event.stopPropagation()}
      >
        <DownloadIcon width={14} height={14} />
        {t('chat.downloadDocument')}
      </a>
    </div>
  )
}

/** Right-hand document pane — Claude-style artifact viewer. */
export function ArtifactPanel() {
  const { t } = useTranslation()
  const { artifact, closeArtifact } = useArtifact()
  const [body, setBody] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [expanded, setExpanded] = useState(false)

  useEffect(() => {
    if (!artifact) {
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

  if (!artifact) return null

  const kind = extensionLabel(artifact.name)

  return (
    <aside
      className={`flex h-full min-h-0 shrink-0 flex-col border-s border-primary-100
        bg-surface shadow-lg animate-chat-in
        ${
          expanded
            ? 'absolute inset-0 z-20 w-full'
            : `absolute inset-0 z-20 w-full
              md:static md:inset-auto md:w-[min(100%,28rem)] lg:w-[32rem]`
        }`}
    >
      <header
        className="flex shrink-0 items-center gap-3 border-b border-secondary-200
          bg-secondary-25 px-4 py-3"
      >
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-semibold text-dark" dir="auto">
            {artifact.name.replace(/\.[^.]+$/, '') || artifact.name}
            <span className="font-normal text-secondary"> · {kind}</span>
          </p>
        </div>
        <a
          href={api.files.downloadUrl(artifact.fileId)}
          download={artifact.name}
          aria-label={t('chat.downloadDocument')}
          className="rounded-lg p-2 text-secondary transition hover:bg-secondary-100
            hover:text-dark"
        >
          <DownloadIcon width={18} height={18} />
        </a>
        <button
          type="button"
          aria-label={expanded ? t('chat.shrinkPreview') : t('chat.expandPreview')}
          onClick={() => setExpanded((value) => !value)}
          className="rounded-lg p-2 text-secondary transition hover:bg-secondary-100
            hover:text-dark"
        >
          <ExpandIcon width={18} height={18} />
        </button>
        <button
          type="button"
          aria-label={t('chat.closePreview')}
          onClick={closeArtifact}
          className="rounded-lg p-2 text-secondary transition hover:bg-secondary-100
            hover:text-dark"
        >
          <CloseIcon width={18} height={18} />
        </button>
      </header>

      <div className="min-h-0 flex-1 overflow-y-auto bg-canvas p-4 sm:p-6">
        <div
          className="mx-auto min-h-full max-w-2xl rounded-sm bg-surface px-8 py-10
            shadow-md ring-1 ring-secondary-200 sm:px-12 sm:py-14"
        >
          {loading && (
            <div className="flex items-center gap-2 text-sm text-secondary">
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
      </div>
    </aside>
  )
}

/** Pull the file id out of a write_file tool result line. */
export function fileIdFromWriteResult(result: string): string | null {
  const match = result.match(/\/api\/files\/([0-9a-f-]{36})\/download/i)
  return match?.[1] ?? null
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

/** @deprecated Use DocumentFileCard — kept name for older imports. */
export const DocumentPreview = DocumentFileCard
