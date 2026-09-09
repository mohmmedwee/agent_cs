import { useTranslation } from 'react-i18next'
import { NavLink, useNavigate, useParams } from 'react-router-dom'

import {
  BrainIcon,
  ChatIcon,
  ChevronIcon,
  FileIcon,
  GearIcon,
  PlusIcon,
  SparkIcon,
  TrashIcon,
  UsersIcon,
} from '@/components/Icons'
import { useAuth } from '@/hooks/useAuth'
import {
  useConversations,
  useCreateConversation,
  useDeleteConversation,
} from '@/hooks/useConversations'

interface Props {
  collapsed: boolean
  onToggle: () => void
}

export function Sidebar({ collapsed, onToggle }: Props) {
  const { t, i18n } = useTranslation()
  const { user } = useAuth()
  const navigate = useNavigate()
  const { id: activeId } = useParams()

  const { data: conversations = [] } = useConversations()
  const create = useCreateConversation()
  const remove = useDeleteConversation()

  const startChat = async () => {
    const created = await create.mutateAsync(undefined)
    navigate(`/chat/${created.id}`)
  }

  const deleteChat = async (id: string) => {
    if (!window.confirm(t('chat.deleteConfirm'))) return
    await remove.mutateAsync(id)
    if (id === activeId) navigate('/chat')
  }

  const links = [
    { to: '/chat', label: t('nav.chat'), Icon: ChatIcon },
    { to: '/files', label: t('nav.files'), Icon: FileIcon },
    { to: '/memory', label: t('nav.memory'), Icon: BrainIcon },
    { to: '/skills', label: t('nav.skills'), Icon: SparkIcon },
    { to: '/settings', label: t('nav.settings'), Icon: GearIcon },
    ...(user?.is_admin
      ? [{ to: '/admin', label: t('nav.admin'), Icon: UsersIcon }]
      : []),
  ]

  return (
    <aside
      className={`flex h-full min-h-0 shrink-0 flex-col border-e border-secondary-200 bg-surface
        transition-[width] duration-200 ${collapsed ? 'w-[72px]' : 'w-60'}`}
    >
      <div className="p-3">
        <button
          type="button"
          onClick={() => void startChat()}
          disabled={create.isPending}
          className="btn-primary w-full px-3"
          title={collapsed ? t('nav.newChat') : undefined}
        >
          <PlusIcon width={18} height={18} />
          {!collapsed && <span className="truncate">{t('nav.newChat')}</span>}
        </button>
      </div>

      <nav className="space-y-0.5 px-3">
        {links.map(({ to, label, Icon }) => (
          <NavLink
            key={to}
            to={to}
            title={collapsed ? label : undefined}
            className={({ isActive }) =>
              `flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-medium
               transition ${
                 isActive
                   ? 'bg-primary-50 text-primary'
                   : 'text-secondary hover:bg-secondary-100 hover:text-dark'
               } ${collapsed ? 'justify-center' : ''}`
            }
          >
            <Icon width={18} height={18} className="shrink-0" />
            {!collapsed && <span className="truncate">{label}</span>}
          </NavLink>
        ))}
      </nav>

      {!collapsed && (
        <div className="mt-5 flex min-h-0 flex-1 flex-col">
          <p className="px-6 pb-1.5 text-xs font-semibold uppercase tracking-wide text-secondary-400">
            {t('nav.conversations')}
          </p>
          <ul className="min-h-0 flex-1 space-y-0.5 overflow-y-auto px-3 pb-3">
            {conversations.map((conversation) => (
              <li key={conversation.id} className="group relative">
                <NavLink
                  to={`/chat/${conversation.id}`}
                  className={({ isActive }) =>
                    `block truncate rounded-xl py-2 pe-9 ps-3 text-sm transition ${
                      isActive
                        ? 'bg-secondary-100 font-medium text-dark'
                        : 'text-secondary hover:bg-secondary-100'
                    }`
                  }
                >
                  {conversation.title}
                </NavLink>
                <button
                  type="button"
                  onClick={() => void deleteChat(conversation.id)}
                  aria-label={t('chat.deleteChat')}
                  className="absolute end-1.5 top-1/2 hidden -translate-y-1/2 rounded-lg p-1.5
                    text-secondary-400 transition hover:bg-error-50 hover:text-error
                    group-hover:block focus-visible:block"
                >
                  <TrashIcon width={15} height={15} />
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}

      <button
        type="button"
        onClick={onToggle}
        className="btn-ghost m-3 mt-auto justify-center"
        aria-label={collapsed ? t('nav.expand') : t('nav.collapse')}
      >
        <ChevronIcon
          width={18}
          height={18}
          // The chevron points outward in LTR and inward in RTL, so it always
          // indicates the direction the panel will actually move.
          className={`transition-transform ${
            collapsed !== (i18n.language === 'ar') ? '' : 'rotate-180'
          }`}
        />
      </button>
    </aside>
  )
}
