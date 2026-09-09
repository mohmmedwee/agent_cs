import { useTranslation } from 'react-i18next'

import arabicLogo from '@/assets/images/arlogo.svg'
import latinLogo from '@/assets/images/logo-3.0.svg'

/** The Cleverso wordmark, in the script matching the active language. */
export function Logo({ className = 'h-8' }: { className?: string }) {
  const { i18n } = useTranslation()
  const arabic = i18n.language === 'ar'

  return (
    <img
      src={arabic ? arabicLogo : latinLogo}
      alt="cleverso-ai"
      className={className}
      draggable={false}
    />
  )
}
