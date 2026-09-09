import { useTranslation } from 'react-i18next'

import { GlobeIcon } from '@/components/Icons'

/**
 * Labelled with the language it switches *to*, in that language — someone who
 * cannot read the current one still recognises their own.
 */
export function LanguageToggle({ compact = false }: { compact?: boolean }) {
  const { i18n } = useTranslation()
  const next = i18n.language === 'ar' ? 'en' : 'ar'
  const label = next === 'ar' ? 'العربية' : 'English'

  return (
    <button
      type="button"
      onClick={() => void i18n.changeLanguage(next)}
      className="btn-ghost gap-1.5 px-3"
      aria-label={`Switch to ${label}`}
      lang={next}
    >
      <GlobeIcon width={16} height={16} />
      {!compact && <span className="text-sm">{label}</span>}
    </button>
  )
}
