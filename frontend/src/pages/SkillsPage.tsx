import { useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useQuery } from '@tanstack/react-query'

import { SearchIcon, SparkIcon, SpinnerIcon } from '@/components/Icons'
import { PageHeader } from '@/components/PageHeader'
import { api } from '@/lib/api'

export function SkillsPage() {
  const { t } = useTranslation()
  const [filter, setFilter] = useState('')

  const { data: skills = [], isLoading } = useQuery({
    queryKey: ['skills'],
    queryFn: api.skills.list,
  })

  const visible = useMemo(() => {
    const needle = filter.trim().toLowerCase()
    if (!needle) return skills
    return skills.filter(
      (skill) =>
        skill.name.toLowerCase().includes(needle) ||
        skill.description.toLowerCase().includes(needle),
    )
  }, [skills, filter])

  return (
    <div className="mx-auto h-full max-w-4xl overflow-y-auto px-6 py-8">
      <PageHeader title={t('skills.title')} subtitle={t('skills.subtitle')} />

      <div className="mb-5 flex flex-wrap items-center gap-3">
        <div className="relative flex-1 min-w-56">
          <SearchIcon
            width={17}
            height={17}
            className="absolute start-3.5 top-1/2 -translate-y-1/2 text-secondary-400"
          />
          <input
            value={filter}
            onChange={(event) => setFilter(event.target.value)}
            placeholder={t('skills.search')}
            aria-label={t('skills.search')}
            className="field ps-11"
          />
        </div>
        <span className="text-sm text-secondary">
          {t('skills.count', { count: skills.length })}
        </span>
      </div>

      {isLoading ? (
        <div className="flex justify-center py-16 text-secondary">
          <SpinnerIcon />
        </div>
      ) : visible.length === 0 ? (
        <div className="card px-6 py-16 text-center text-sm text-secondary">
          {t('skills.empty')}
        </div>
      ) : (
        <ul className="grid gap-3 sm:grid-cols-2">
          {visible.map((skill) => (
            <li key={skill.name} className="card p-4">
              <div className="flex items-start gap-2.5">
                <SparkIcon width={17} height={17} className="mt-0.5 shrink-0 text-primary" />
                <div className="min-w-0">
                  <h2 className="truncate font-mono text-sm font-semibold text-dark">
                    {skill.name}
                  </h2>
                  <p className="mt-1 text-sm leading-relaxed text-secondary" dir="auto">
                    {skill.description}
                  </p>
                </div>
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
