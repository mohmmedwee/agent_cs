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
 * Quiet Workbench auth: paper ground, bordered card, flat primary.
 */
export function AuthLayout({ title, subtitle, children, footer }: Props) {
  return (
    <div className="min-h-dvh bg-paper">
      <div className="flex items-center justify-between px-6 py-5">
        <div className="inline-flex items-center gap-2.5">
          <Logo className="h-7" />
          <span className="text-sm font-semibold tracking-tight text-ink">
            cleverso-ai
          </span>
        </div>
        <LanguageToggle />
      </div>

      <div className="flex justify-center px-4 pb-16 pt-6">
        <div
          className="w-full max-w-[442px] rounded-[20px] border border-line bg-surface
            p-8 shadow-sm"
        >
          <h1 className="text-2xl font-semibold text-ink">{title}</h1>
          <p className="mt-1.5 text-sm text-ink-2">{subtitle}</p>
          <div className="mt-7">{children}</div>
          <div className="mt-6 text-center text-sm text-ink-2">{footer}</div>
        </div>
      </div>
    </div>
  )
}
