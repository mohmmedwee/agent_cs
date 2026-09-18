import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { EyeIcon, EyeOffIcon } from '@/components/Icons'

interface Props {
  id: string
  value: string
  onChange: (value: string) => void
  placeholder?: string
  autoComplete?: string
}

/**
 * The Cleverso pattern uses an eye icon rather than the words Show/Hide, so
 * the control does not change width or need translating.
 */
export function PasswordField({
  id,
  value,
  onChange,
  placeholder,
  autoComplete = 'current-password',
}: Props) {
  const { t } = useTranslation()
  const [visible, setVisible] = useState(false)

  return (
    <div className="relative">
      <input
        id={id}
        type={visible ? 'text' : 'password'}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        placeholder={placeholder}
        autoComplete={autoComplete}
        required
        className="field pe-11"
        dir="ltr"
      />
      <button
        type="button"
        onClick={() => setVisible((shown) => !shown)}
        aria-label={visible ? t('auth.hidePassword') : t('auth.showPassword')}
        className="absolute end-3 top-1/2 -translate-y-1/2 text-ink-3
          transition hover:text-ink-2"
      >
        {visible ? <EyeOffIcon width={18} height={18} /> : <EyeIcon width={18} height={18} />}
      </button>
    </div>
  )
}
