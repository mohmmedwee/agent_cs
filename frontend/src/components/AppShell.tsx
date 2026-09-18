import { useState } from 'react'
import { Outlet, useLocation } from 'react-router-dom'

import { ConversationList } from '@/components/ConversationList'
import { NavRail } from '@/components/NavRail'
import { useLocalSetting } from '@/hooks/useLocalSetting'

export type AppShellOutlet = {
  conversationsCollapsed: boolean
  setConversationsCollapsed: (collapsed: boolean) => void
  openMobileConversations: () => void
}

/**
 * Quiet Workbench shell: dark rail + optional conversations panel + main.
 */
export function AppShell() {
  const location = useLocation()
  const [collapsed, setCollapsed] = useLocalSetting('sidebar-collapsed', false)
  const [mobileDrawer, setMobileDrawer] = useState(false)
  const isChatRoute = location.pathname.startsWith('/chat')

  return (
    <div className="flex h-dvh bg-paper">
      <NavRail />
      {isChatRoute && !collapsed && (
        <div className="hidden md:flex">
          <ConversationList onCollapse={() => setCollapsed(true)} />
        </div>
      )}
      {isChatRoute && (
        <div className="md:hidden">
          <ConversationList
            onCollapse={() => setMobileDrawer(false)}
            mobileOpen={mobileDrawer}
            onMobileClose={() => setMobileDrawer(false)}
          />
        </div>
      )}
      <main className="relative min-h-0 min-w-0 flex-1 overflow-hidden bg-paper-2 pb-16 md:pb-0">
        <Outlet
          context={
            {
              conversationsCollapsed: collapsed,
              setConversationsCollapsed: setCollapsed,
              openMobileConversations: () => setMobileDrawer(true),
            } satisfies AppShellOutlet
          }
        />
      </main>
    </div>
  )
}
