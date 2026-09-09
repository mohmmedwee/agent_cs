import { useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { DownloadIcon, PaperclipIcon, SpinnerIcon, TrashIcon } from '@/components/Icons'
import { PageHeader } from '@/components/PageHeader'
import { api } from '@/lib/api'
import type { StoredFile } from '@/types'

function humanSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`
}

export function FilesPage() {
  const { t, i18n } = useTranslation()
  const queryClient = useQueryClient()
  const picker = useRef<HTMLInputElement>(null)
  const [dragging, setDragging] = useState(false)

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

      {isLoading ? (
        <div className="flex justify-center py-16 text-secondary">
          <SpinnerIcon />
        </div>
      ) : files.length === 0 ? (
        <div className="card px-6 py-16 text-center text-sm text-secondary">
          {t('files.empty')}
        </div>
      ) : (
        <div className="card overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-secondary-25 text-xs uppercase tracking-wide text-secondary">
              <tr>
                <th className="px-4 py-3 text-start font-semibold">{t('files.name')}</th>
                <th className="px-4 py-3 text-start font-semibold">{t('files.size')}</th>
                <th className="px-4 py-3 text-start font-semibold">{t('files.state')}</th>
                <th className="px-4 py-3 text-start font-semibold">{t('files.uploaded')}</th>
                <th className="px-4 py-3 text-end font-semibold">{t('files.actions')}</th>
              </tr>
            </thead>
            <tbody>
              {files.map((file) => (
                <tr key={file.id} className="border-t border-secondary-200">
                  <td className="max-w-xs truncate px-4 py-3 font-medium" dir="auto">
                    {file.name}
                  </td>
                  <td className="whitespace-nowrap px-4 py-3 text-secondary">
                    {humanSize(file.size)}
                  </td>
                  <td className="px-4 py-3">
                    <span
                      className={`whitespace-nowrap rounded-full px-2.5 py-1 text-xs
                        font-medium ${
                          file.is_image
                            ? 'bg-primary-50 text-primary'
                            : file.is_text
                              ? 'bg-success-50 text-success'
                              : 'bg-secondary-100 text-secondary'
                        }`}
                    >
                      {file.is_image
                        ? t('files.viewable')
                        : file.is_text
                          ? t('files.readable')
                          : t('files.binary')}
                    </span>
                  </td>
                  <td className="whitespace-nowrap px-4 py-3 text-secondary">
                    {dateFormat.format(new Date(file.uploaded_at))}
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex justify-end gap-1">
                      <a
                        href={api.files.downloadUrl(file.id)}
                        download={file.name}
                        aria-label={t('files.download')}
                        className="rounded-lg p-2 text-secondary transition
                          hover:bg-secondary-100 hover:text-dark"
                      >
                        <DownloadIcon width={16} height={16} />
                      </a>
                      <button
                        type="button"
                        onClick={() => confirmDelete(file)}
                        aria-label={t('files.delete')}
                        className="rounded-lg p-2 text-secondary transition
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
