import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useNavigate } from 'react-router-dom'

import { useAuth } from '@/hooks/useAuth'

/**
 * Initials from a real display name (first letter of up to two words).
 * Never derive two letters from the email — "me@…" must show "M", not "ME".
 * Treat email-shaped or email-local display names as missing.
 */
function initials(displayName: string | undefined, email: string): string {
  const local = (email.trim().split('@')[0] || email.trim()).trim()
  const localLower = local.toLowerCase()
  const name = (displayName ?? '').trim()
  const looksLikeEmail = name.includes('@')
  const nameLower = name.toLowerCase()
  const isEmailLocal =
    !looksLikeEmail &&
    Boolean(name) &&
    (nameLower === localLower || nameLower.replace(/[._-]+/g, '') === localLower.replace(/[._-]+/g, ''))

  if (name && !looksLikeEmail && !isEmailLocal) {
    const parts = name.split(/\s+/).filter(Boolean).slice(0, 2)
    // "M E" / "m.e" style placeholders that mirror the email local-part → email fallback.
    const joined = parts.join('').replace(/[._-]+/g, '').toLowerCase()
    if (parts.length >= 2 && joined === localLower.replace(/[._-]+/g, '')) {
      return (local[0] ?? '?').toUpperCase()
    }
    const chars = parts.map((part) => part[0]?.toUpperCase() ?? '').join('')
    if (chars) return chars
  }
  return (local[0] ?? '?').toUpperCase()
}

interface Props {
  /** Rail avatar sits at the bottom of the dark nav; menu opens to the inline-end. */
  variant?: 'default' | 'rail'
}

export function ProfileMenu({ variant = 'default' }: Props) {
  const { user, logout } = useAuth()
  const { t } = useTranslation()
  const navigate = useNavigate()
  const [open, setOpen] = useState(false)
  const container = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!open) return
    const onPointerDown = (event: MouseEvent) => {
      if (!container.current?.contains(event.target as Node)) setOpen(false)
    }
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setOpen(false)
    }
    document.addEventListener('mousedown', onPointerDown)
    document.addEventListener('keydown', onKeyDown)
    return () => {
      document.removeEventListener('mousedown', onPointerDown)
      document.removeEventListener('keydown', onKeyDown)
    }
  }, [open])

  if (!user) return null

  const signOut = async () => {
    setOpen(false)
    await logout()
    navigate('/login', { replace: true })
  }

  const rail = variant === 'rail'

  return (
    <div className="relative" ref={container}>
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label={user.display_name}
        className={
          rail
            ? `flex size-9 items-center justify-center rounded-full bg-violet-tint
                text-xs font-bold text-violet-ink transition hover:opacity-90`
            : `flex size-9 items-center justify-center rounded-full bg-paper-3
                text-sm font-semibold text-ink transition hover:bg-paper-4`
        }
      >
        {initials(user.display_name, user.email)}
      </button>

      {open && (
        <div
          role="menu"
          className={
            rail
              ? `absolute bottom-0 start-full z-50 ms-2 w-60 rounded-2xl border
                  border-line bg-elevated p-1.5 shadow-lg`
              : `absolute end-0 top-11 z-50 w-60 rounded-2xl border
                  border-line bg-elevated p-1.5 shadow-lg`
          }
        >
          <div className="border-b border-line px-3 py-2.5">
            <p className="truncate text-sm font-semibold text-ink">{user.display_name}</p>
            <p className="truncate text-xs text-ink-2" dir="ltr">
              {user.email}
            </p>
          </div>
          <button
            type="button"
            role="menuitem"
            onClick={() => void signOut()}
            className="mt-1 w-full rounded-xl px-3 py-2 text-start text-sm
              text-error transition hover:bg-error-50"
          >
            {t('auth.signOut')}
          </button>
        </div>
      )}
    </div>
  )
}
