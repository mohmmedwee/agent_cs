import { useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import {
  EditIcon,
  PlusIcon,
  SearchIcon,
  SparkIcon,
  SpinnerIcon,
  TrashIcon,
} from '@/components/Icons'
import { Markdown } from '@/components/chat/Markdown'
import { PageHeader } from '@/components/PageHeader'
import { api, ApiError } from '@/lib/api'
import type { Skill, UserSkill } from '@/types'

type Draft = {
  name: string
  description: string
  body: string
  enabled: boolean
}

type Scope = 'all' | 'yours' | 'builtin'
type BodyMode = 'write' | 'preview'

const emptyDraft = (): Draft => ({
  name: '',
  description: '',
  body: '',
  enabled: true,
})

/** Match backend slugify: "Oustah Guidelines" → "oustah-guidelines". */
function slugifySkillName(name: string): string {
  return name
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
    .slice(0, 63)
}

export function SkillsPage() {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const [filter, setFilter] = useState('')
  const [scope, setScope] = useState<Scope>('all')
  const [editor, setEditor] = useState<'create' | string | null>(null)
  const [draft, setDraft] = useState<Draft>(emptyDraft)
  const [idea, setIdea] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [showAdvanced, setShowAdvanced] = useState(false)
  const [bodyMode, setBodyMode] = useState<BodyMode>('write')
  const [expandedId, setExpandedId] = useState<string | null>(null)
  const [expandedBody, setExpandedBody] = useState<string | null>(null)
  const [expandedLoading, setExpandedLoading] = useState(false)

  const { data: skills = [], isLoading } = useQuery({
    queryKey: ['skills'],
    queryFn: api.skills.list,
  })

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ['skills'] })

  const create = useMutation({
    mutationFn: (payload: Draft) => api.skills.create(payload),
    onSuccess: () => {
      setEditor(null)
      setDraft(emptyDraft())
      setIdea('')
      setShowAdvanced(false)
      setError(null)
      invalidate()
    },
    onError: (err: Error) => {
      setError(err instanceof ApiError ? err.message : t('skills.saveFailed'))
    },
  })

  const update = useMutation({
    mutationFn: ({ id, payload }: { id: string; payload: Omit<Draft, 'name'> }) =>
      api.skills.update(id, payload),
    onSuccess: () => {
      setEditor(null)
      setDraft(emptyDraft())
      setIdea('')
      setShowAdvanced(false)
      setError(null)
      invalidate()
    },
    onError: (err: Error) => {
      setError(err instanceof ApiError ? err.message : t('skills.saveFailed'))
    },
  })

  const generate = useMutation({
    mutationFn: (prompt: string) => api.skills.generate(prompt),
    onSuccess: (result) => {
      setDraft({
        name: result.name,
        description: result.description,
        body: result.body,
        enabled: true,
      })
      setShowAdvanced(true)
      setBodyMode('preview')
      setError(null)
    },
    onError: (err: Error) => {
      setError(err instanceof ApiError ? err.message : t('skills.generateFailed'))
    },
  })

  const remove = useMutation({
    mutationFn: (id: string) => api.skills.remove(id),
    onSuccess: invalidate,
  })

  const toggleEnabled = useMutation({
    mutationFn: ({ id, enabled }: { id: string; enabled: boolean }) =>
      api.skills.update(id, { enabled }),
    onSuccess: invalidate,
  })

  const openCreate = () => {
    setError(null)
    setDraft(emptyDraft())
    setIdea('')
    setShowAdvanced(false)
    setBodyMode('write')
    setEditor('create')
    setScope('yours')
  }

  const openEdit = async (skill: Skill) => {
    if (skill.source !== 'user' || !skill.id) return
    setError(null)
    setIdea('')
    try {
      const full: UserSkill = await api.skills.get(skill.id)
      setDraft({
        name: full.name,
        description: full.description,
        body: full.body,
        enabled: full.enabled,
      })
      setShowAdvanced(true)
      setBodyMode('preview')
      setEditor(full.id)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : t('skills.saveFailed'))
    }
  }

  const toggleExpand = async (skill: Skill) => {
    if (!skill.id) return
    if (expandedId === skill.id) {
      setExpandedId(null)
      setExpandedBody(null)
      return
    }
    setExpandedId(skill.id)
    setExpandedLoading(true)
    setExpandedBody(null)
    try {
      const full = await api.skills.get(skill.id)
      setExpandedBody(full.body)
    } catch {
      setExpandedBody(null)
      setExpandedId(null)
    } finally {
      setExpandedLoading(false)
    }
  }

  const closeEditor = () => {
    setEditor(null)
    setError(null)
    setIdea('')
    setShowAdvanced(false)
    setBodyMode('write')
  }

  const submit = () => {
    if (editor === 'create') {
      create.mutate({ ...draft, name: slugifySkillName(draft.name) })
      return
    }
    if (typeof editor === 'string') {
      update.mutate({
        id: editor,
        payload: {
          description: draft.description,
          body: draft.body,
          enabled: draft.enabled,
        },
      })
    }
  }

  const nameSlug = slugifySkillName(draft.name)

  const counts = useMemo(() => {
    const yours = skills.filter((s) => s.source === 'user').length
    const builtin = skills.filter((s) => s.source !== 'user').length
    return { all: skills.length, yours, builtin }
  }, [skills])

  const visible = useMemo(() => {
    const needle = filter.trim().toLowerCase()
    return skills.filter((skill) => {
      if (scope === 'yours' && skill.source !== 'user') return false
      if (scope === 'builtin' && skill.source === 'user') return false
      if (!needle) return true
      return (
        skill.name.toLowerCase().includes(needle) ||
        skill.description.toLowerCase().includes(needle)
      )
    })
  }, [skills, filter, scope])

  const yours = visible.filter((s) => s.source === 'user')
  const builtins = visible.filter((s) => s.source !== 'user')
  const saving = create.isPending || update.isPending
  const canSave =
    Boolean(draft.description.trim() && draft.body.trim()) &&
    (editor !== 'create' || Boolean(nameSlug))

  const scopes: { id: Scope; label: string; count: number }[] = [
    { id: 'all', label: t('skills.filterAll'), count: counts.all },
    { id: 'yours', label: t('skills.filterYours'), count: counts.yours },
    { id: 'builtin', label: t('skills.filterBuiltin'), count: counts.builtin },
  ]

  return (
    <div className="mx-auto h-full max-w-3xl overflow-y-auto px-6 py-8">
      <PageHeader title={t('skills.title')} subtitle={t('skills.subtitle')} />

      <div className="mb-4 flex flex-wrap items-center gap-2">
        {scopes.map((item) => (
          <button
            key={item.id}
            type="button"
            onClick={() => setScope(item.id)}
            className={[
              'rounded-xl px-3 py-1.5 text-xs font-medium transition',
              scope === item.id
                ? 'bg-primary text-white'
                : 'border border-line bg-surface text-ink-2 hover:border-primary/40 hover:text-ink',
            ].join(' ')}
          >
            {item.label}
            <span className="ms-1.5 opacity-70">{item.count}</span>
          </button>
        ))}
        <div className="ms-auto">
          <button
            type="button"
            onClick={openCreate}
            className="btn-primary shrink-0 !px-4 !py-2 text-xs"
          >
            <PlusIcon width={14} height={14} />
            {t('skills.add')}
          </button>
        </div>
      </div>

      <div className="relative mb-5">
        <SearchIcon
          width={17}
          height={17}
          className="absolute start-3.5 top-1/2 -translate-y-1/2 text-ink-3"
        />
        <input
          value={filter}
          onChange={(event) => setFilter(event.target.value)}
          placeholder={t('skills.search')}
          aria-label={t('skills.search')}
          className="field ps-11"
        />
      </div>

      {editor ? (
        <div className="card mb-6 space-y-4 p-5">
          <div className="flex items-start justify-between gap-3">
            <div>
              <h2 className="text-sm font-semibold text-ink">
                {editor === 'create' ? t('skills.addTitle') : t('skills.editTitle')}
              </h2>
              <p className="mt-0.5 text-xs text-ink-2">{t('skills.aiHint')}</p>
            </div>
            <button
              type="button"
              onClick={closeEditor}
              className="text-xs font-medium text-ink-2 hover:text-ink"
            >
              {t('skills.cancel')}
            </button>
          </div>

          {editor === 'create' ? (
            <div className="rounded-2xl border border-primary/20 bg-primary-25/40 p-3">
              <label className="mb-1.5 flex items-center gap-1.5 text-xs font-medium text-ink">
                <SparkIcon width={14} height={14} className="text-primary" />
                {t('skills.aiLabel')}
              </label>
              <textarea
                value={idea}
                onChange={(event) => setIdea(event.target.value)}
                rows={3}
                dir="auto"
                placeholder={t('skills.aiPlaceholder')}
                className="field min-h-[4.5rem] resize-y text-sm"
              />
              <div className="mt-2 flex flex-wrap items-center gap-2">
                <button
                  type="button"
                  disabled={idea.trim().length < 3 || generate.isPending}
                  onClick={() => generate.mutate(idea.trim())}
                  className="btn-primary !px-4 !py-2 text-xs"
                >
                  {generate.isPending ? (
                    <SpinnerIcon width={14} height={14} />
                  ) : (
                    <SparkIcon width={14} height={14} />
                  )}
                  {generate.isPending
                    ? t('skills.generating')
                    : t('skills.generate')}
                </button>
                <button
                  type="button"
                  onClick={() => {
                    setShowAdvanced(true)
                    setBodyMode('write')
                  }}
                  className="rounded-xl border border-line px-3 py-1.5 text-xs font-medium text-ink-2"
                >
                  {t('skills.writeMyself')}
                </button>
              </div>
            </div>
          ) : null}

          {showAdvanced || editor !== 'create' ? (
            <div className="space-y-3">
              {editor === 'create' ? (
                <div>
                  <label className="mb-1 block text-xs font-medium text-ink">
                    {t('skills.name')}
                  </label>
                  <input
                    value={draft.name}
                    onChange={(event) =>
                      setDraft((prev) => ({ ...prev, name: event.target.value }))
                    }
                    placeholder={t('skills.namePlaceholder')}
                    className="field font-mono text-sm"
                    autoComplete="off"
                    spellCheck={false}
                  />
                  <p className="mt-1 text-[11px] text-ink-2">
                    {nameSlug
                      ? t('skills.namePreview', { name: nameSlug })
                      : t('skills.nameHint')}
                  </p>
                </div>
              ) : (
                <p className="font-mono text-sm font-semibold text-ink">{draft.name}</p>
              )}
              <div>
                <label className="mb-1 block text-xs font-medium text-ink">
                  {t('skills.description')}
                </label>
                <input
                  value={draft.description}
                  onChange={(event) =>
                    setDraft((prev) => ({
                      ...prev,
                      description: event.target.value,
                    }))
                  }
                  placeholder={t('skills.descriptionPlaceholder')}
                  dir="auto"
                  className="field text-sm"
                />
              </div>
              <div>
                <div className="mb-1.5 flex flex-wrap items-center justify-between gap-2">
                  <label className="text-xs font-medium text-ink">
                    {t('skills.body')}
                  </label>
                  <div className="flex rounded-lg border border-line p-0.5">
                    <button
                      type="button"
                      onClick={() => setBodyMode('write')}
                      className={[
                        'rounded-md px-2.5 py-1 text-[11px] font-medium transition',
                        bodyMode === 'write'
                          ? 'bg-primary text-white'
                          : 'text-ink-2 hover:text-ink',
                      ].join(' ')}
                    >
                      {t('skills.bodyWrite')}
                    </button>
                    <button
                      type="button"
                      onClick={() => setBodyMode('preview')}
                      className={[
                        'rounded-md px-2.5 py-1 text-[11px] font-medium transition',
                        bodyMode === 'preview'
                          ? 'bg-primary text-white'
                          : 'text-ink-2 hover:text-ink',
                      ].join(' ')}
                    >
                      {t('skills.bodyPreview')}
                    </button>
                  </div>
                </div>
                {bodyMode === 'write' ? (
                  <textarea
                    value={draft.body}
                    onChange={(event) =>
                      setDraft((prev) => ({ ...prev, body: event.target.value }))
                    }
                    rows={10}
                    dir="auto"
                    placeholder={t('skills.bodyPlaceholder')}
                    className="field min-h-[12rem] resize-y font-mono text-sm leading-relaxed"
                  />
                ) : draft.body.trim() ? (
                  <div
                    dir="auto"
                    className="min-h-[12rem] rounded-xl border border-line bg-surface px-4 py-3"
                  >
                    <Markdown text={draft.body} />
                  </div>
                ) : (
                  <p className="rounded-xl border border-dashed border-line px-4 py-8 text-center text-sm text-ink-2">
                    {t('skills.bodyPreviewEmpty')}
                  </p>
                )}
              </div>
              <label className="flex items-center gap-2 text-sm text-ink">
                <input
                  type="checkbox"
                  checked={draft.enabled}
                  onChange={(event) =>
                    setDraft((prev) => ({
                      ...prev,
                      enabled: event.target.checked,
                    }))
                  }
                  className="rounded border-line"
                />
                {t('skills.enabled')}
              </label>
            </div>
          ) : null}

          {error ? (
            <p role="alert" className="text-xs text-error">
              {error}
            </p>
          ) : null}

          {(showAdvanced || editor !== 'create') && (
            <div className="flex flex-wrap gap-2 border-t border-line pt-3">
              <button
                type="button"
                disabled={saving || !canSave}
                onClick={submit}
                className="btn-primary !px-4 !py-2 text-xs"
              >
                {saving ? <SpinnerIcon width={14} height={14} /> : null}
                {t('skills.save')}
              </button>
              {editor === 'create' && idea.trim().length >= 3 ? (
                <button
                  type="button"
                  disabled={generate.isPending}
                  onClick={() => generate.mutate(idea.trim())}
                  className="rounded-xl border border-line px-3 py-1.5 text-xs font-medium text-ink-2"
                >
                  {t('skills.regenerate')}
                </button>
              ) : null}
            </div>
          )}
        </div>
      ) : null}

      {isLoading ? (
        <div className="flex justify-center py-16 text-ink-2">
          <SpinnerIcon />
        </div>
      ) : !editor && visible.length === 0 ? (
        <div className="rounded-2xl border border-dashed border-line px-6 py-14 text-center">
          <p className="text-sm text-ink-2">{t('skills.empty')}</p>
          {scope !== 'builtin' ? (
            <button
              type="button"
              onClick={openCreate}
              className="btn-primary mt-4 !px-4 !py-2 text-xs"
            >
              <PlusIcon width={14} height={14} />
              {t('skills.add')}
            </button>
          ) : null}
        </div>
      ) : !editor ? (
        <div className="space-y-6">
          {yours.length > 0 ? (
            <section>
              {scope === 'all' ? (
                <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-ink-3">
                  {t('skills.sectionYours')}
                </h3>
              ) : null}
              <ul className="space-y-2">
                {yours.map((skill) => (
                  <SkillRow
                    key={skill.id ?? skill.name}
                    skill={skill}
                    expanded={expandedId === skill.id}
                    expandedBody={expandedId === skill.id ? expandedBody : null}
                    expandedLoading={expandedId === skill.id && expandedLoading}
                    onExpand={() => toggleExpand(skill)}
                    onEdit={() => openEdit(skill)}
                    onDelete={() => {
                      if (skill.id && window.confirm(t('skills.deleteConfirm'))) {
                        remove.mutate(skill.id)
                      }
                    }}
                    onToggle={() => {
                      if (!skill.id) return
                      toggleEnabled.mutate({
                        id: skill.id,
                        enabled: !(skill.enabled !== false),
                      })
                    }}
                    t={t}
                  />
                ))}
              </ul>
            </section>
          ) : null}

          {builtins.length > 0 ? (
            <section>
              {scope === 'all' ? (
                <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-ink-3">
                  {t('skills.sectionBuiltin')}
                </h3>
              ) : null}
              <ul className="space-y-2">
                {builtins.map((skill) => (
                  <SkillRow key={`builtin-${skill.name}`} skill={skill} t={t} />
                ))}
              </ul>
            </section>
          ) : null}
        </div>
      ) : null}
    </div>
  )
}

function SkillRow({
  skill,
  expanded,
  expandedBody,
  expandedLoading,
  onExpand,
  onEdit,
  onDelete,
  onToggle,
  t,
}: {
  skill: Skill
  expanded?: boolean
  expandedBody?: string | null
  expandedLoading?: boolean
  onExpand?: () => void
  onEdit?: () => void
  onDelete?: () => void
  onToggle?: () => void
  t: (key: string) => string
}) {
  const isUser = skill.source === 'user'
  const enabled = skill.enabled !== false

  return (
    <li
      className={[
        'rounded-2xl border border-line bg-surface px-4 py-3 transition',
        !enabled ? 'opacity-60' : '',
      ].join(' ')}
    >
      <div className="flex items-start gap-3">
        <SparkIcon
          width={16}
          height={16}
          className="mt-0.5 shrink-0 text-primary"
        />
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <h2 className="truncate font-mono text-sm font-semibold text-ink">
              {skill.name}
            </h2>
            {!isUser ? (
              <span className="rounded-md bg-surface-2 px-1.5 py-0.5 text-[10px] font-medium text-ink-2">
                {t('skills.builtin')}
              </span>
            ) : null}
            {isUser && !enabled ? (
              <span className="rounded-md bg-surface-2 px-1.5 py-0.5 text-[10px] font-medium text-ink-2">
                {t('skills.disabled')}
              </span>
            ) : null}
          </div>
          <p className="mt-1 text-sm leading-relaxed text-ink-2" dir="auto">
            {skill.description}
          </p>
          {isUser && onExpand ? (
            <button
              type="button"
              onClick={onExpand}
              className="mt-2 text-[11px] font-medium text-primary hover:underline"
            >
              {expanded ? t('skills.hideBody') : t('skills.showBody')}
            </button>
          ) : null}
          {expanded ? (
            <div className="mt-3 rounded-xl border border-line bg-canvas px-3 py-2" dir="auto">
              {expandedLoading ? (
                <div className="flex justify-center py-6 text-ink-2">
                  <SpinnerIcon width={16} height={16} />
                </div>
              ) : expandedBody ? (
                <Markdown text={expandedBody} compact />
              ) : (
                <p className="py-4 text-center text-xs text-ink-2">
                  {t('skills.bodyPreviewEmpty')}
                </p>
              )}
            </div>
          ) : null}
        </div>
        {isUser ? (
          <div className="flex shrink-0 items-center gap-0.5">
            {onToggle ? (
              <button
                type="button"
                onClick={onToggle}
                className={[
                  'rounded-lg px-2 py-1 text-[11px] font-medium transition',
                  enabled
                    ? 'text-primary hover:bg-primary-25'
                    : 'text-ink-2 hover:bg-surface-2',
                ].join(' ')}
              >
                {enabled ? t('skills.on') : t('skills.off')}
              </button>
            ) : null}
            {onEdit ? (
              <button
                type="button"
                aria-label={t('skills.edit')}
                onClick={onEdit}
                className="rounded-lg p-1.5 text-ink-2 transition hover:bg-primary-25 hover:text-primary"
              >
                <EditIcon width={14} height={14} />
              </button>
            ) : null}
            {onDelete ? (
              <button
                type="button"
                aria-label={t('skills.delete')}
                onClick={onDelete}
                className="rounded-lg p-1.5 text-ink-2 transition hover:bg-error-50 hover:text-error"
              >
                <TrashIcon width={14} height={14} />
              </button>
            ) : null}
          </div>
        ) : null}
      </div>
    </li>
  )
}
