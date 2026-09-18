import { NavLink, useLocation, useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'

import {
  BrainIcon,
  ChatIcon,
  FileIcon,
  GearIcon,
  PlusIcon,
  SparkIcon,
  UsersIcon,
} from '@/components/Icons'
import { LanguageToggle } from '@/components/LanguageToggle'
import { ProfileMenu } from '@/components/ProfileMenu'
import { useAuth } from '@/hooks/useAuth'
import { useCreateConversation } from '@/hooks/useConversations'
import { useLocalSetting } from '@/hooks/useLocalSetting'

export function NavRail() {
  const { t } = useTranslation()
  const { user } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const create = useCreateConversation()
  const [conversationsCollapsed] = useLocalSetting('sidebar-collapsed', false)
  const isChatRoute = location.pathname.startsWith('/chat')
  // Conversations panel owns the language pill on chat; rail shows it elsewhere
  // (and when the panel is collapsed).
  const showLanguageInRail = !isChatRoute || conversationsCollapsed

  const startChat = async () => {
    const created = await create.mutateAsync(undefined)
    navigate(`/chat/${created.id}`)
  }

  const mainLinks = [
    { to: '/chat', label: t('nav.chat'), Icon: ChatIcon, match: (path: string) => path.startsWith('/chat') },
    { to: '/files', label: t('nav.files'), Icon: FileIcon, match: (path: string) => path.startsWith('/files') },
    { to: '/memory', label: t('nav.memory'), Icon: BrainIcon, match: (path: string) => path.startsWith('/memory') },
    { to: '/skills', label: t('nav.skills'), Icon: SparkIcon, match: (path: string) => path.startsWith('/skills') },
  ]

  const mobileLinks = [
    ...mainLinks,
    { to: '/settings', label: t('nav.settings'), Icon: GearIcon, match: (path: string) => path.startsWith('/settings') },
  ]

  return (
    <>
      <nav
        aria-label={t('nav.main')}
        className="hidden h-full w-[68px] shrink-0 flex-col items-center gap-1.5 bg-rail py-4 md:flex"
      >
        <button
          type="button"
          onClick={() => void startChat()}
          disabled={create.isPending}
          aria-label={t('nav.newChat')}
          title={t('nav.newChat')}
          className="mb-3.5 flex size-11 items-center justify-center rounded-[14px]
            bg-primary text-white transition hover:bg-primary-600
            disabled:cursor-not-allowed disabled:opacity-60"
        >
          <PlusIcon width={18} height={18} />
        </button>

        {mainLinks.map(({ to, label, Icon, match }) => {
          const active = match(location.pathname)
          return (
            <NavLink
              key={to}
              to={to}
              aria-label={label}
              title={label}
              className={`flex size-11 items-center justify-center rounded-xl transition ${
                active
                  ? 'bg-rail-active text-white'
                  : 'text-rail-icon hover:bg-rail-active/60 hover:text-white'
              }`}
            >
              <Icon width={18} height={18} />
            </NavLink>
          )
        })}

        <div className="flex-1" />

        {showLanguageInRail ? <LanguageToggle variant="rail" /> : null}

        {user?.is_admin && (
          <NavLink
            to="/admin"
            aria-label={t('nav.admin')}
            title={t('nav.admin')}
            className={({ isActive }) =>
              `flex size-11 items-center justify-center rounded-xl transition ${
                isActive
                  ? 'bg-rail-active text-white'
                  : 'text-rail-icon hover:bg-rail-active/60 hover:text-white'
              }`
            }
          >
            <UsersIcon width={18} height={18} />
          </NavLink>
        )}

        <NavLink
          to="/settings"
          aria-label={t('nav.settings')}
          title={t('nav.settings')}
          className={({ isActive }) =>
            `flex size-11 items-center justify-center rounded-xl transition ${
              isActive
                ? 'bg-rail-active text-white'
                : 'text-rail-icon hover:bg-rail-active/60 hover:text-white'
            }`
          }
        >
          <GearIcon width={18} height={18} />
        </NavLink>

        <div className="mt-1.5">
          <ProfileMenu variant="rail" />
        </div>
      </nav>

      <nav
        aria-label={t('nav.main')}
        className="fixed inset-x-0 bottom-0 z-40 flex h-16 items-stretch
          border-t border-rail-active bg-rail pb-[env(safe-area-inset-bottom)] md:hidden"
      >
        {mobileLinks.map(({ to, label, Icon, match }) => {
          const active = match(location.pathname)
          return (
            <NavLink
              key={to}
              to={to}
              className={`flex min-w-[44px] flex-1 flex-col items-center justify-center gap-0.5
                text-[10px] transition ${
                  active ? 'text-white' : 'text-rail-icon'
                }`}
            >
              <Icon width={18} height={18} />
              <span>{label}</span>
            </NavLink>
          )
        })}
      </nav>
    </>
  )
}
