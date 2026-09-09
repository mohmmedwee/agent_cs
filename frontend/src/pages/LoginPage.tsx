import { useState, type FormEvent } from 'react'
import { useTranslation } from 'react-i18next'
import { Link, useLocation, useNavigate } from 'react-router-dom'

import { AuthLayout } from '@/components/AuthLayout'
import { PasswordField } from '@/components/PasswordField'
import { SpinnerIcon } from '@/components/Icons'
import { useAuth } from '@/hooks/useAuth'

export function LoginPage() {
  const { t } = useTranslation()
  const { login } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()

  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const submit = async (event: FormEvent) => {
    event.preventDefault()
    setError(null)
    setBusy(true)
    try {
      await login(email, password)
      // Return them to whatever they were trying to reach before the guard
      // intercepted, not to a generic landing page.
      const target = (location.state as { from?: string } | null)?.from ?? '/chat'
      navigate(target, { replace: true })
    } catch (problem) {
      setError((problem as Error).message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <AuthLayout
      title={t('auth.loginTitle')}
      subtitle={t('auth.loginSubtitle')}
      footer={
        <>
          {t('auth.noAccount')}{' '}
          <Link to="/register" className="font-semibold text-primary hover:underline">
            {t('auth.signUp')}
          </Link>
        </>
      }
    >
      <form onSubmit={submit} className="space-y-4" noValidate>
        <div>
          <label htmlFor="email" className="mb-1.5 block text-sm font-medium">
            {t('auth.email')}
          </label>
          <input
            id="email"
            type="email"
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            placeholder={t('auth.emailPlaceholder')}
            autoComplete="email"
            required
            className="field"
            dir="ltr"
          />
        </div>

        <div>
          <label htmlFor="password" className="mb-1.5 block text-sm font-medium">
            {t('auth.password')}
          </label>
          <PasswordField id="password" value={password} onChange={setPassword} />
        </div>

        {error && (
          <p role="alert" className="rounded-xl bg-error-50 px-4 py-2.5 text-sm text-error">
            {error}
          </p>
        )}

        <button type="submit" disabled={busy} className="btn-primary w-full">
          {busy && <SpinnerIcon width={16} height={16} />}
          {busy ? t('auth.signingIn') : t('auth.signIn')}
        </button>
      </form>
    </AuthLayout>
  )
}
