import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useNavigate } from 'react-router-dom'

import { useAuth } from '@/hooks/useAuth'

function initials(name: string): string {
  const parts = name.trim().split(/\s+/).slice(0, 2)
  return parts.map((part) => part[0]?.toUpperCase() ?? '').join('') || '?'
}

export function ProfileMenu() {
  const { user, logout } = useAuth()
  const { t } = useTranslation()
  const navigate = useNavigate()
  const [open, setOpen] = useState(false)
  const container = useRef<HTMLDivElement>(null)

  // A menu that only closes on its own button is a trap for pointer users and
  // for anyone who reaches for Escape.
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

  return (
    <div className="relative" ref={container}>
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        aria-haspopup="menu"
        aria-expanded={open}
        className="flex size-9 items-center justify-center rounded-full bg-primary-50
          text-sm font-semibold text-primary transition hover:bg-primary-100"
      >
        {initials(user.display_name)}
      </button>

      {open && (
        <div
          role="menu"
          className="absolute end-0 top-11 z-50 w-60 rounded-2xl border
            border-secondary-200 bg-elevated p-1.5 shadow-lg"
        >
          <div className="border-b border-secondary-200 px-3 py-2.5">
            <p className="truncate text-sm font-semibold">{user.display_name}</p>
            <p className="truncate text-xs text-secondary" dir="ltr">
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
