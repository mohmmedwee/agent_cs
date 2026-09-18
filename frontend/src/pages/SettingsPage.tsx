import { useTranslation } from 'react-i18next'
import { useQuery } from '@tanstack/react-query'

import { PageHeader } from '@/components/PageHeader'
import { useLocalSetting } from '@/hooks/useLocalSetting'
import { useTheme } from '@/hooks/useTheme'
import { LOCALES, type Locale } from '@/i18n'
import { api } from '@/lib/api'
import { normalizeEffort, type Effort } from '@/types'

const EFFORTS: Effort[] = ['minimal', 'low', 'medium', 'xhigh']

function Section({
  title,
  help,
  children,
}: {
  title: string
  help?: string
  children: React.ReactNode
}) {
  return (
    <section className="card p-5">
      <h2 className="font-semibold text-dark">{title}</h2>
      {help && <p className="mt-1 text-sm text-secondary">{help}</p>}
      <div className="mt-4">{children}</div>
    </section>
  )
}

export function SettingsPage() {
  const { t, i18n } = useTranslation()
  const [model, setModel] = useLocalSetting<string | null>('model', null)
  const [storedEffort, setEffort] = useLocalSetting<string>('effort', 'medium')
  const effort = normalizeEffort(storedEffort)
  const { theme, setTheme } = useTheme()

  const { data } = useQuery({ queryKey: ['models'], queryFn: api.models })
  const models = data?.models ?? []

  return (
    <div className="mx-auto h-full max-w-2xl overflow-y-auto px-6 py-8">
      <PageHeader title={t('settings.title')} subtitle={t('settings.subtitle')} />

      <div className="space-y-4">
        <Section title={t('settings.model')} help={t('settings.modelHelp')}>
          {models.length === 0 ? (
            <p className="text-sm text-secondary">{t('settings.modelUnavailable')}</p>
          ) : (
            <select
              value={model ?? data?.current ?? ''}
              onChange={(event) => setModel(event.target.value || null)}
              className="field"
              dir="ltr"
            >
              {models.map((entry) => (
                <option key={entry.id} value={entry.id}>
                  {entry.id}
                  {entry.loaded ? ' ●' : ''}
                </option>
              ))}
            </select>
          )}
        </Section>

        <Section title={t('settings.effort')} help={t('settings.effortHelp')}>
          <div className="space-y-2">
            {EFFORTS.map((level) => {
              const selected = effort === level
              return (
                <label
                  key={level}
                  className={`flex cursor-pointer items-start gap-3 rounded-xl border p-3.5
                    transition ${
                      selected
                        ? 'border-primary-300 bg-primary-25'
                        : 'border-secondary-200 hover:bg-secondary-25'
                    }`}
                >
                  <input
                    type="radio"
                    name="effort"
                    value={level}
                    checked={selected}
                    onChange={() => setEffort(level)}
                    className="mt-0.5 accent-[var(--color-primary)]"
                  />
                  <span>
                    <span className="block text-sm font-medium text-dark">
                      {t(
                        level === 'xhigh'
                          ? 'settings.effortXhigh'
                          : `settings.effort${level.charAt(0).toUpperCase()}${level.slice(1)}`,
                      )}
                    </span>
                    <span className="mt-0.5 block text-xs text-secondary">
                      {t(
                        level === 'xhigh'
                          ? 'settings.effortXhighHelp'
                          : `settings.effort${level.charAt(0).toUpperCase()}${level.slice(1)}Help`,
                      )}
                    </span>
                  </span>
                </label>
              )
            })}
          </div>
        </Section>

        <Section title={t('settings.appearance')}>
          <div className="space-y-4">
            <div>
              <p className="mb-2 text-sm font-medium">{t('settings.theme')}</p>
              <div className="inline-flex rounded-xl border border-secondary-200 p-1">
                {(['light', 'dark'] as const).map((option) => (
                  <button
                    key={option}
                    type="button"
                    onClick={() => setTheme(option)}
                    className={`rounded-lg px-4 py-1.5 text-sm transition ${
                      theme === option
                        ? 'bg-primary text-white'
                        : 'text-secondary hover:text-dark'
                    }`}
                  >
                    {t(`settings.theme${option === 'light' ? 'Light' : 'Dark'}`)}
                  </button>
                ))}
              </div>
            </div>

            <div>
              <p className="mb-2 text-sm font-medium">{t('settings.language')}</p>
              <div className="inline-flex rounded-xl border border-secondary-200 p-1">
                {LOCALES.map((locale: Locale) => (
                  <button
                    key={locale}
                    type="button"
                    onClick={() => void i18n.changeLanguage(locale)}
                    lang={locale}
                    className={`rounded-lg px-4 py-1.5 text-sm transition ${
                      i18n.language === locale
                        ? 'bg-primary text-white'
                        : 'text-secondary hover:text-dark'
                    }`}
                  >
                    {locale === 'ar' ? 'العربية' : 'English'}
                  </button>
                ))}
              </div>
            </div>
          </div>
        </Section>
      </div>
    </div>
  )
}
