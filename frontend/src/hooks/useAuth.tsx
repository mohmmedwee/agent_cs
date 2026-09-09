import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react'
import { useQueryClient } from '@tanstack/react-query'

import { ApiError, api } from '@/lib/api'
import type { User } from '@/types'

interface AuthState {
  user: User | null
  /** True only until the first /me call settles, so guards can wait it out. */
  loading: boolean
  login: (email: string, password: string) => Promise<void>
  register: (email: string, name: string, password: string) => Promise<void>
  logout: () => Promise<void>
}

const AuthContext = createContext<AuthState | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [loading, setLoading] = useState(true)
  const queryClient = useQueryClient()

  // The cookie is HTTP-only, so the only way to know whether a session exists
  // is to ask the server once on mount.
  useEffect(() => {
    let cancelled = false
    api.auth
      .me()
      .then((me) => !cancelled && setUser(me))
      .catch((error) => {
        if (!(error instanceof ApiError && error.isUnauthorized)) {
          console.error('session check failed', error)
        }
      })
      .finally(() => !cancelled && setLoading(false))
    return () => {
      cancelled = true
    }
  }, [])

  const login = useCallback(async (email: string, password: string) => {
    setUser(await api.auth.login(email, password))
  }, [])

  const register = useCallback(
    async (email: string, name: string, password: string) => {
      setUser(await api.auth.register(email, name, password))
    },
    [],
  )

  const logout = useCallback(async () => {
    await api.auth.logout()
    setUser(null)
    // Otherwise the next person to sign in briefly sees the previous user's
    // conversations and files from cache.
    queryClient.clear()
  }, [queryClient])

  const value = useMemo(
    () => ({ user, loading, login, register, logout }),
    [user, loading, login, register, logout],
  )

  return <AuthContext value={value}>{children}</AuthContext>
}

export function useAuth() {
  const context = useContext(AuthContext)
  if (!context) throw new Error('useAuth must be used inside AuthProvider')
  return context
}
