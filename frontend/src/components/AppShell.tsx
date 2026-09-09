import { Outlet } from 'react-router-dom'

import { LanguageToggle } from '@/components/LanguageToggle'
import { Logo } from '@/components/Logo'
import { ProfileMenu } from '@/components/ProfileMenu'
import { Sidebar } from '@/components/Sidebar'
import { useLocalSetting } from '@/hooks/useLocalSetting'

export function AppShell() {
  const [collapsed, setCollapsed] = useLocalSetting('sidebar-collapsed', false)

  return (
    <div className="flex h-dvh flex-col bg-canvas">
      <header
        className="sticky top-0 z-40 flex h-16 shrink-0 items-center justify-between
          border-b border-secondary-200 bg-glassy px-5 backdrop-blur-md"
      >
        <Logo className="h-7" />
        <div className="flex items-center gap-1">
          <LanguageToggle />
          <ProfileMenu />
        </div>
      </header>

      <div className="flex min-h-0 flex-1">
        <Sidebar collapsed={collapsed} onToggle={() => setCollapsed(!collapsed)} />
        {/* min-w-0 stops long code blocks in chat from stretching the layout. */}
        <main className="min-w-0 flex-1 overflow-y-auto">
          <Outlet />
        </main>
      </div>
    </div>
  )
}
