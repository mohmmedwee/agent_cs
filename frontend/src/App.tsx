import { Navigate, Route, Routes, useLocation } from 'react-router-dom'
import type { ReactElement } from 'react'

import { AppShell } from '@/components/AppShell'
import { SpinnerIcon } from '@/components/Icons'
import { useAuth } from '@/hooks/useAuth'
import { useTheme } from '@/hooks/useTheme'
import { AdminPage } from '@/pages/AdminPage'
import { ChatPage } from '@/pages/ChatPage'
import { FilesPage } from '@/pages/FilesPage'
import { LoginPage } from '@/pages/LoginPage'
import { RegisterPage } from '@/pages/RegisterPage'
import { MemoryPage } from '@/pages/MemoryPage'
import { SettingsPage } from '@/pages/SettingsPage'
import { SkillsPage } from '@/pages/SkillsPage'

function FullPageSpinner() {
  return (
    <div className="flex h-dvh items-center justify-center text-secondary">
      <SpinnerIcon width={28} height={28} />
    </div>
  )
}

/**
 * Waits for the session check before deciding.
 *
 * Redirecting while `loading` is still true would bounce every signed-in user
 * to the login screen on each page load, since the cookie can only be verified
 * by asking the server.
 */
function RequireAuth({ children, adminOnly = false }: { children: ReactElement; adminOnly?: boolean }) {
  const { user, loading } = useAuth()
  const location = useLocation()

  if (loading) return <FullPageSpinner />
  if (!user) return <Navigate to="/login" replace state={{ from: location.pathname }} />
  if (adminOnly && !user.is_admin) return <Navigate to="/chat" replace />
  return children
}

/** Signed-in users have no use for the auth screens. */
function RequireAnonymous({ children }: { children: ReactElement }) {
  const { user, loading } = useAuth()
  if (loading) return <FullPageSpinner />
  return user ? <Navigate to="/chat" replace /> : children
}

export default function App() {
  useTheme() // applies the saved theme on first paint

  return (
    <Routes>
      <Route
        path="/login"
        element={
          <RequireAnonymous>
            <LoginPage />
          </RequireAnonymous>
        }
      />
      <Route
        path="/register"
        element={
          <RequireAnonymous>
            <RegisterPage />
          </RequireAnonymous>
        }
      />

      <Route
        element={
          <RequireAuth>
            <AppShell />
          </RequireAuth>
        }
      >
        <Route path="/chat" element={<ChatPage />} />
        <Route path="/chat/:id" element={<ChatPage />} />
        <Route path="/files" element={<FilesPage />} />
        <Route path="/memory" element={<MemoryPage />} />
        <Route path="/skills" element={<SkillsPage />} />
        <Route path="/settings" element={<SettingsPage />} />
        <Route
          path="/admin"
          element={
            <RequireAuth adminOnly>
              <AdminPage />
            </RequireAuth>
          }
        />
      </Route>

      <Route path="*" element={<Navigate to="/chat" replace />} />
    </Routes>
  )
}
