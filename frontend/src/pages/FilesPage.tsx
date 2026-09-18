import { useMemo, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import {
  fileBadgeClass,
  isImageFileName,
} from '@/components/chat/DocumentPreview'
import {
  DownloadIcon,
  PaperclipIcon,
  SearchIcon,
  SpinnerIcon,
  TrashIcon,
} from '@/components/Icons'
import { PageHeader } from '@/components/PageHeader'
import { api } from '@/lib/api'
import type { StoredFile } from '@/types'

type FileFilter = 'all' | 'documents' | 'spreadsheets' | 'images' | 'other'

function humanSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`
}

function fileExt(name: string): string {
  const leaf = name.includes('.') ? name.split('.').pop()!.toLowerCase() : ''
  return leaf
}

function badgeShort(name: string): string {
  const lower = name.toLowerCase()
  if (lower.endsWith('.docx') || lower.endsWith('.doc')) return 'DOC'
  if (lower.endsWith('.xlsx') || lower.endsWith('.xls')) return 'XLS'
  const ext = fileExt(name)
  if (!ext) return 'FILE'
  if (ext.length <= 4) return ext.toUpperCase()
  return ext.slice(0, 3).toUpperCase()
}

function fileKind(name: string): Exclude<FileFilter, 'all'> {
  const ext = fileExt(name)
  if (isImageFileName(name)) return 'images'
  if (['xlsx', 'xls', 'csv'].includes(ext)) return 'spreadsheets'
  if (['doc', 'docx', 'pdf', 'txt', 'md', 'rtf', 'odt', 'html', 'htm'].includes(ext)) {
    return 'documents'
  }
  return 'other'
}

const FILTERS: FileFilter[] = ['all', 'documents', 'spreadsheets', 'images', 'other']

export function FilesPage() {
  const { t, i18n } = useTranslation()
  const queryClient = useQueryClient()
  const picker = useRef<HTMLInputElement>(null)
  const [dragging, setDragging] = useState(false)
  const [query, setQuery] = useState('')
  const [filter, setFilter] = useState<FileFilter>('all')

  const { data: files = [], isLoading } = useQuery({
    queryKey: ['files'],
    queryFn: api.files.list,
  })

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ['files'] })

  const upload = useMutation({
    mutationFn: (chosen: File[]) => api.files.upload(chosen),
    onSuccess: invalidate,
  })
  const remove = useMutation({
    mutationFn: (id: string) => api.files.remove(id),
    onSuccess: invalidate,
  })

  const confirmDelete = (file: StoredFile) => {
    if (window.confirm(t('files.deleteConfirm', { name: file.name }))) {
      remove.mutate(file.id)
    }
  }

  const dateFormat = new Intl.DateTimeFormat(i18n.language, {
    dateStyle: 'medium',
    timeStyle: 'short',
  })

  const visible = useMemo(() => {
    const needle = query.trim().toLowerCase()
    return files.filter((file) => {
      if (needle && !file.name.toLowerCase().includes(needle)) return false
      if (filter !== 'all' && fileKind(file.name) !== filter) return false
      return true
    })
  }, [files, query, filter])

  const filterLabel = (key: FileFilter): string => {
    switch (key) {
      case 'all':
        return t('files.filterAll')
      case 'documents':
        return t('files.filterDocuments')
      case 'spreadsheets':
        return t('files.filterSpreadsheets')
      case 'images':
        return t('files.filterImages')
      case 'other':
        return t('files.filterOther')
    }
  }

  return (
    <div
      className="relative mx-auto h-full max-w-4xl overflow-y-auto px-6 py-8"
      onDragOver={(event) => {
        event.preventDefault()
        setDragging(true)
      }}
      onDragLeave={(event) => {
        if (!event.currentTarget.contains(event.relatedTarget as Node)) setDragging(false)
      }}
      onDrop={(event) => {
        event.preventDefault()
        setDragging(false)
        const dropped = Array.from(event.dataTransfer.files)
        if (dropped.length) upload.mutate(dropped)
      }}
    >
      {dragging && (
        <div
          className="pointer-events-none absolute inset-4 z-30 flex items-center
            justify-center rounded-2xl border-2 border-dashed border-primary-300
            bg-primary-25/90 text-sm font-medium text-primary"
        >
          {t('files.dropHere')}
        </div>
      )}

      <PageHeader
        title={t('files.title')}
        subtitle={t('files.subtitle')}
        actions={
          <>
            <input
              ref={picker}
              type="file"
              multiple
              hidden
              onChange={(event) => {
                const chosen = Array.from(event.target.files ?? [])
                if (chosen.length) upload.mutate(chosen)
                event.target.value = ''
              }}
            />
            <button
              type="button"
              onClick={() => picker.current?.click()}
              disabled={upload.isPending}
              className="btn-primary"
            >
              {upload.isPending ? (
                <SpinnerIcon width={17} height={17} />
              ) : (
                <PaperclipIcon width={17} height={17} />
              )}
              {t('files.upload')}
            </button>
          </>
        }
      />

      {!isLoading && files.length > 0 ? (
        <div className="mb-4 flex flex-wrap items-center gap-3">
          <div className="relative w-full max-w-[320px]">
            <SearchIcon
              width={16}
              height={16}
              className="pointer-events-none absolute start-3 top-1/2 -translate-y-1/2
                text-ink-3"
            />
            <input
              type="search"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder={t('files.search')}
              aria-label={t('files.search')}
              className="field w-full ps-9"
            />
          </div>
          <div className="flex flex-wrap items-center gap-1.5">
            {FILTERS.map((key) => {
              const active = filter === key
              return (
                <button
                  key={key}
                  type="button"
                  onClick={() => setFilter(key)}
                  className={`h-8 rounded-full border px-3 text-xs transition ${
                    active
                      ? 'border-violet-line bg-violet-tint font-semibold text-violet-ink'
                      : 'border-line text-ink-2'
                  }`}
                >
                  {filterLabel(key)}
                </button>
              )
            })}
          </div>
        </div>
      ) : null}

      {isLoading ? (
        <div className="flex justify-center py-16 text-ink-2">
          <SpinnerIcon />
        </div>
      ) : files.length === 0 ? (
        <div className="card px-6 py-16 text-center text-sm text-ink-2">
          {t('files.empty')}
        </div>
      ) : visible.length === 0 ? (
        <p className="text-sm text-ink-3">{t('files.noFilterResults')}</p>
      ) : (
        <div className="overflow-hidden rounded-[14px] border border-line bg-surface">
          <table className="w-full text-sm">
            <thead
              className="bg-paper-3 text-[11px] uppercase tracking-[0.06em] text-ink-3
                rtl:normal-case rtl:tracking-normal"
            >
              <tr>
                <th className="px-4 py-3 text-start font-semibold">{t('files.name')}</th>
                <th className="px-4 py-3 text-start font-semibold">{t('files.size')}</th>
                <th className="px-4 py-3 text-start font-semibold">{t('files.uploaded')}</th>
                <th className="px-4 py-3 text-end font-semibold">{t('files.actions')}</th>
              </tr>
            </thead>
            <tbody>
              {visible.map((file) => (
                <tr
                  key={file.id}
                  className="h-14 border-t border-line transition hover:bg-paper-2"
                >
                  <td className="px-4 py-2">
                    <div className="flex min-w-0 items-center gap-3">
                      <div
                        className={`flex size-8 shrink-0 items-center justify-center
                          rounded-[10px] text-[10px] font-bold ${fileBadgeClass(file.name)}`}
                      >
                        {badgeShort(file.name)}
                      </div>
                      <span
                        className="min-w-0 truncate text-[13px] font-semibold text-ink"
                        dir="auto"
                      >
                        {file.name}
                      </span>
                    </div>
                  </td>
                  <td className="whitespace-nowrap px-4 py-2 text-ink-2">
                    {humanSize(file.size)}
                  </td>
                  <td className="whitespace-nowrap px-4 py-2 text-ink-2">
                    {dateFormat.format(new Date(file.uploaded_at))}
                  </td>
                  <td className="px-4 py-2">
                    <div className="flex justify-end gap-1.5">
                      <a
                        href={api.files.downloadUrl(file.id)}
                        download={file.name}
                        aria-label={t('files.download')}
                        className="inline-flex size-9 items-center justify-center
                          rounded-[10px] border border-line text-ink-2 transition
                          hover:bg-paper-3 hover:text-ink"
                      >
                        <DownloadIcon width={16} height={16} />
                      </a>
                      <button
                        type="button"
                        onClick={() => confirmDelete(file)}
                        aria-label={t('files.delete')}
                        className="inline-flex size-9 items-center justify-center
                          rounded-[10px] border border-line text-ink-2 transition
                          hover:bg-error-50 hover:text-error"
                      >
                        <TrashIcon width={16} height={16} />
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
