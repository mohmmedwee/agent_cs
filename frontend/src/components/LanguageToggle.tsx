import { useTranslation } from 'react-i18next'

import { GlobeIcon } from '@/components/Icons'

/**
 * Labelled with the language it switches *to*, in that language — someone who
 * cannot read the current one still recognises their own.
 */
export function LanguageToggle({
  compact = false,
  variant = 'default',
  className,
}: {
  compact?: boolean
  /** Text-only control for the dark nav rail (non-chat routes). */
  variant?: 'default' | 'rail'
  className?: string
}) {
  const { t, i18n } = useTranslation()
  const next = i18n.language === 'ar' ? 'en' : 'ar'
  const label = next === 'ar' ? 'العربية' : 'English'
  const short = next === 'ar' ? 'ع' : 'EN'
  const switchLabel =
    next === 'ar' ? t('nav.switchToArabic') : t('nav.switchToEnglish')

  if (variant === 'rail') {
    return (
      <button
        type="button"
        onClick={() => void i18n.changeLanguage(next)}
        aria-label={switchLabel}
        title={switchLabel}
        lang={next}
        className={
          className ??
          `flex size-11 items-center justify-center rounded-xl text-sm font-semibold
            text-rail-icon transition hover:bg-rail-active/60 hover:text-white`
        }
      >
        {short}
      </button>
    )
  }

  return (
    <button
      type="button"
      onClick={() => void i18n.changeLanguage(next)}
      className={
        className ??
        (compact
          ? `inline-flex h-[30px] items-center gap-1 whitespace-nowrap rounded-full
              border border-line bg-surface px-2.5 text-xs font-semibold leading-none
              text-ink-2 transition hover:bg-paper-3 hover:text-ink`
          : `btn-ghost inline-flex items-center gap-1.5 whitespace-nowrap px-3`)
      }
      aria-label={switchLabel}
      lang={next}
    >
      <GlobeIcon width={compact ? 14 : 16} height={compact ? 14 : 16} className="shrink-0" />
      {compact ? (
        <span className="inline-flex items-center leading-none">{short}</span>
      ) : (
        <span className="text-sm">{label}</span>
      )}
    </button>
  )
}
