import { useState, type FormEvent } from 'react'
import { useTranslation } from 'react-i18next'
import { Link, useNavigate } from 'react-router-dom'

import { AuthLayout } from '@/components/AuthLayout'
import { PasswordField } from '@/components/PasswordField'
import { SpinnerIcon } from '@/components/Icons'
import { useAuth } from '@/hooks/useAuth'

const MIN_PASSWORD = 8

export function RegisterPage() {
  const { t } = useTranslation()
  const { register } = useAuth()
  const navigate = useNavigate()

  const [email, setEmail] = useState('')
  const [name, setName] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const submit = async (event: FormEvent) => {
    event.preventDefault()
    // Checked here as well as server-side, so the mistake is caught before a
    // round-trip rather than after it.
    if (password.length < MIN_PASSWORD) {
      setError(t('auth.passwordTooShort'))
      return
    }
    setError(null)
    setBusy(true)
    try {
      await register(email, name, password)
      navigate('/chat', { replace: true })
    } catch (problem) {
      setError((problem as Error).message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <AuthLayout
      title={t('auth.registerTitle')}
      subtitle={t('auth.registerSubtitle')}
      footer={
        <>
          {t('auth.haveAccount')}{' '}
          <Link to="/login" className="font-semibold text-primary hover:underline">
            {t('auth.signIn')}
          </Link>
        </>
      }
    >
      <form onSubmit={submit} className="space-y-4" noValidate>
        <div>
          <label htmlFor="name" className="mb-1.5 block text-sm font-medium">
            {t('auth.name')}
          </label>
          <input
            id="name"
            value={name}
            onChange={(event) => setName(event.target.value)}
            placeholder={t('auth.namePlaceholder')}
            autoComplete="name"
            required
            className="field"
          />
        </div>

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
          <PasswordField
            id="password"
            value={password}
            onChange={setPassword}
            placeholder={t('auth.passwordPlaceholder')}
            autoComplete="new-password"
          />
        </div>

        {error && (
          <p role="alert" className="rounded-xl bg-error-50 px-4 py-2.5 text-sm text-error">
            {error}
          </p>
        )}

        <button type="submit" disabled={busy} className="btn-primary w-full">
          {busy && <SpinnerIcon width={16} height={16} />}
          {busy ? t('auth.creating') : t('auth.signUp')}
        </button>
      </form>
    </AuthLayout>
  )
}
