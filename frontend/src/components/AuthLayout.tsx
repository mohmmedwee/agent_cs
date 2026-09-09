import type { ReactNode } from 'react'

import { LanguageToggle } from '@/components/LanguageToggle'
import { Logo } from '@/components/Logo'

interface Props {
  title: string
  subtitle: string
  children: ReactNode
  footer: ReactNode
}

/**
 * The Cleverso auth pattern: lavender gradient, one centred card, with the
 * logo and language toggle outside the card so they read as chrome.
 */
export function AuthLayout({ title, subtitle, children, footer }: Props) {
  return (
    <div className="min-h-dvh bg-gradient-to-b from-primary-50 via-primary-25 to-canvas">
      <div className="flex items-center justify-between px-6 py-5">
        <div className="inline-flex items-center gap-2.5">
          <Logo className="h-7" />
          <span className="text-sm font-semibold tracking-tight text-primary">
            cleverso-ai
          </span>
        </div>
        <LanguageToggle />
      </div>

      <div className="flex justify-center px-4 pb-16 pt-6">
        <div className="w-full max-w-[442px] rounded-3xl bg-surface px-10 pb-10 pt-8 shadow-lg">
          <h1 className="text-2xl font-semibold text-dark">{title}</h1>
          <p className="mt-1.5 text-sm text-secondary">{subtitle}</p>
          <div className="mt-7">{children}</div>
          <div className="mt-6 text-center text-sm text-secondary">{footer}</div>
        </div>
      </div>
    </div>
  )
}
