import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { EditIcon, PlusIcon, SpinnerIcon, TrashIcon } from '@/components/Icons'
import { PageHeader } from '@/components/PageHeader'
import { api, ApiError } from '@/lib/api'

export function MemoryPage() {
  const { t, i18n } = useTranslation()
  const queryClient = useQueryClient()
  const [draft, setDraft] = useState('')
  const [editingId, setEditingId] = useState<string | null>(null)
  const [editText, setEditText] = useState('')
  const [error, setError] = useState<string | null>(null)

  const { data: memories = [], isLoading } = useQuery({
    queryKey: ['memory'],
    queryFn: api.memory.list,
  })

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ['memory'] })

  const create = useMutation({
    mutationFn: (content: string) => api.memory.create(content),
    onSuccess: () => {
      setDraft('')
      setError(null)
      invalidate()
    },
    onError: (err: Error) => {
      setError(err instanceof ApiError ? err.message : t('memory.saveFailed'))
    },
  })

  const update = useMutation({
    mutationFn: ({ id, content }: { id: string; content: string }) =>
      api.memory.update(id, content),
    onSuccess: () => {
      setEditingId(null)
      setEditText('')
      setError(null)
      invalidate()
    },
    onError: (err: Error) => {
      setError(err instanceof ApiError ? err.message : t('memory.saveFailed'))
    },
  })

  const remove = useMutation({
    mutationFn: (id: string) => api.memory.remove(id),
    onSuccess: invalidate,
  })

  const dateFormat = new Intl.DateTimeFormat(i18n.language, {
    dateStyle: 'medium',
    timeStyle: 'short',
  })

  const submitNew = () => {
    const content = draft.trim()
    if (!content) return
    create.mutate(content)
  }

  return (
    <div className="mx-auto h-full max-w-2xl overflow-y-auto px-6 py-8">
      <PageHeader title={t('memory.title')} subtitle={t('memory.subtitle')} />

      <div className="card mb-4 p-4">
        <label className="mb-2 block text-sm font-medium text-dark">
          {t('memory.addLabel')}
        </label>
        <textarea
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          rows={2}
          dir="auto"
          placeholder={t('memory.addPlaceholder')}
          className="field min-h-[4.5rem] resize-y"
        />
        <div className="mt-3 flex items-center justify-between gap-3">
          <p className="text-xs text-secondary">{t('memory.addHint')}</p>
          <button
            type="button"
            onClick={submitNew}
            disabled={!draft.trim() || create.isPending}
            className="btn-primary shrink-0 !px-4 !py-2 text-xs"
          >
            {create.isPending ? <SpinnerIcon width={14} height={14} /> : <PlusIcon width={14} height={14} />}
            {t('memory.add')}
          </button>
        </div>
        {error ? (
          <p role="alert" className="mt-2 text-xs text-error">
            {error}
          </p>
        ) : null}
      </div>

      {isLoading ? (
        <div className="flex justify-center py-12 text-secondary">
          <SpinnerIcon />
        </div>
      ) : memories.length === 0 ? (
        <p className="rounded-2xl border border-dashed border-secondary-200 px-4 py-10
          text-center text-sm text-secondary">
          {t('memory.empty')}
        </p>
      ) : (
        <ul className="space-y-2">
          {memories.map((memory) => (
            <li
              key={memory.id}
              className="rounded-2xl border border-secondary-200 bg-surface px-4 py-3"
            >
              {editingId === memory.id ? (
                <div className="space-y-2">
                  <textarea
                    value={editText}
                    onChange={(event) => setEditText(event.target.value)}
                    rows={2}
                    dir="auto"
                    className="field min-h-[4rem] resize-y"
                  />
                  <div className="flex flex-wrap gap-2">
                    <button
                      type="button"
                      disabled={!editText.trim() || update.isPending}
                      onClick={() =>
                        update.mutate({ id: memory.id, content: editText.trim() })
                      }
                      className="btn-primary !px-3 !py-1.5 text-xs"
                    >
                      {t('memory.save')}
                    </button>
                    <button
                      type="button"
                      onClick={() => {
                        setEditingId(null)
                        setEditText('')
                      }}
                      className="rounded-xl border border-secondary-200 px-3 py-1.5
                        text-xs font-medium text-secondary"
                    >
                      {t('memory.cancel')}
                    </button>
                  </div>
                </div>
              ) : (
                <>
                  <p className="text-sm text-dark" dir="auto">
                    {memory.content}
                  </p>
                  <div className="mt-2 flex flex-wrap items-center justify-between gap-2">
                    <p className="text-[11px] text-secondary">
                      {t('memory.meta', {
                        source:
                          memory.source === 'user'
                            ? t('memory.sourceUser')
                            : t('memory.sourceAgent'),
                        when: dateFormat.format(new Date(memory.updated_at)),
                      })}
                    </p>
                    <div className="flex items-center gap-1">
                      <button
                        type="button"
                        aria-label={t('memory.edit')}
                        onClick={() => {
                          setEditingId(memory.id)
                          setEditText(memory.content)
                        }}
                        className="rounded-lg p-1.5 text-secondary transition hover:bg-primary-25
                          hover:text-primary"
                      >
                        <EditIcon width={14} height={14} />
                      </button>
                      <button
                        type="button"
                        aria-label={t('memory.delete')}
                        onClick={() => {
                          if (window.confirm(t('memory.deleteConfirm'))) {
                            remove.mutate(memory.id)
                          }
                        }}
                        className="rounded-lg p-1.5 text-secondary transition hover:bg-error-50
                          hover:text-error"
                      >
                        <TrashIcon width={14} height={14} />
                      </button>
                    </div>
                  </div>
                </>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
