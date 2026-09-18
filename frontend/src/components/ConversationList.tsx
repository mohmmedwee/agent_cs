import { useEffect, useMemo, useRef, useState, useSyncExternalStore } from 'react'
import { useTranslation } from 'react-i18next'
import { NavLink, useLocation, useNavigate } from 'react-router-dom'

import { ConfirmDialog } from '@/components/ConfirmDialog'
import { LanguageToggle } from '@/components/LanguageToggle'
import { Logo } from '@/components/Logo'
import { PanelCollapseIcon, SearchIcon, TrashIcon } from '@/components/Icons'
import {
  useConversations,
  useDeleteConversation,
} from '@/hooks/useConversations'
import { groupConversations } from '@/lib/groupConversations'
import { isChatBusy, subscribeChatRun } from '@/lib/chatRunner'

interface Props {
  onCollapse: () => void
  mobileOpen?: boolean
  onMobileClose?: () => void
}

function useBusyTick(conversationId: string): boolean {
  return useSyncExternalStore(
    (listener) => subscribeChatRun(conversationId, listener),
    () => isChatBusy(conversationId),
    () => false,
  )
}

function ConversationRow({
  id,
  title,
  onDelete,
}: {
  id: string
  title: string
  onDelete: () => void
}) {
  const { t } = useTranslation()
  const busy = useBusyTick(id)

  return (
    <li className="group relative">
      <NavLink
        to={`/chat/${id}`}
        className={({ isActive }) =>
          `flex h-9 items-center gap-2 rounded-[10px] px-2.5 text-[13px] transition ${
            isActive
              ? 'bg-surface font-semibold text-ink shadow-[0_1px_2px_rgb(28_26_36/0.08),0_0_0_1px_var(--color-line)]'
              : 'text-[#3D3A47] hover:bg-paper-3 dark:text-ink-2'
          }`
        }
      >
        <span className="min-w-0 flex-1 truncate" dir="auto">
          {title}
        </span>
        {busy && (
          <span
            className="pointer-events-none flex shrink-0 items-center gap-1.5
              group-hover:hidden group-focus-within:hidden"
          >
            <span
              className="size-[7px] rounded-full bg-primary ring-[3px] ring-violet-tint
                animate-pulse motion-reduce:animate-none"
            />
            <span className="text-[11px] font-semibold text-violet-ink">
              {t('nav.running')}
            </span>
          </span>
        )}
      </NavLink>
      <button
        type="button"
        onClick={(event) => {
          event.preventDefault()
          event.stopPropagation()
          onDelete()
        }}
        aria-label={t('chat.deleteChat')}
        className="absolute end-1.5 top-1/2 z-10 hidden size-7 -translate-y-1/2 items-center
          justify-center rounded-lg text-ink-3 transition hover:bg-error-50 hover:text-error
          group-hover:flex group-focus-within:flex focus-visible:flex"
      >
        <TrashIcon width={15} height={15} />
      </button>
    </li>
  )
}

export function ConversationList({ onCollapse, mobileOpen, onMobileClose }: Props) {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const location = useLocation()
  const activeId = location.pathname.startsWith('/chat/')
    ? location.pathname.slice('/chat/'.length).split('/')[0] || undefined
    : undefined
  const { data: conversations = [] } = useConversations()
  const remove = useDeleteConversation()
  const [pendingDeleteId, setPendingDeleteId] = useState<string | null>(null)
  const [query, setQuery] = useState('')
  const searchRef = useRef<HTMLInputElement>(null)
  const panelRef = useRef<HTMLElement>(null)

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (!(event.metaKey || event.ctrlKey) || event.key.toLowerCase() !== 'k') return
      const tag = (event.target as HTMLElement | null)?.tagName
      if (tag === 'INPUT' || tag === 'TEXTAREA' || (event.target as HTMLElement)?.isContentEditable) {
        return
      }
      event.preventDefault()
      searchRef.current?.focus()
    }
    document.addEventListener('keydown', onKeyDown)
    return () => document.removeEventListener('keydown', onKeyDown)
  }, [])

  useEffect(() => {
    if (!mobileOpen) return
    const root = panelRef.current
    if (!root) return
    const previous = document.activeElement as HTMLElement | null
    const focusables = () =>
      Array.from(
        root.querySelectorAll<HTMLElement>(
          'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])',
        ),
      ).filter((node) => !node.hasAttribute('disabled') && node.tabIndex !== -1)

    const first = focusables()[0]
    first?.focus()

    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.preventDefault()
        onMobileClose?.()
        return
      }
      if (event.key !== 'Tab') return
      const list = focusables()
      if (list.length === 0) return
      const start = list[0]
      const end = list[list.length - 1]
      if (event.shiftKey && document.activeElement === start) {
        event.preventDefault()
        end.focus()
      } else if (!event.shiftKey && document.activeElement === end) {
        event.preventDefault()
        start.focus()
      }
    }
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('keydown', onKey)
      previous?.focus?.()
    }
  }, [mobileOpen, onMobileClose])

  const filtered = useMemo(() => {
    const listed = conversations.filter(
      (conversation) =>
        conversation.id === activeId || conversation.title.trim() !== 'New chat',
    )
    const q = query.trim().toLowerCase()
    if (!q) return listed
    return listed.filter((c) => c.title.toLowerCase().includes(q))
  }, [conversations, query, activeId])

  const groups = useMemo(() => groupConversations(filtered), [filtered])

  const confirmDelete = async () => {
    if (!pendingDeleteId) return
    const id = pendingDeleteId
    const remaining = conversations.filter((conversation) => conversation.id !== id)
    try {
      await remove.mutateAsync(id)
      setPendingDeleteId(null)
      if (id === activeId) {
        navigate(remaining[0] ? `/chat/${remaining[0].id}` : '/chat')
      }
      onMobileClose?.()
    } catch {
      // Keep dialog open for retry.
    }
  }

  const groupLabel = (key: string) => {
    switch (key) {
      case 'today':
        return t('nav.groupToday')
      case 'yesterday':
        return t('nav.groupYesterday')
      case 'week':
        return t('nav.groupWeek')
      default:
        return t('nav.groupOlder')
    }
  }

  const panel = (
    <aside
      ref={panelRef}
      aria-label={t('nav.conversations')}
      className="flex h-full w-[260px] shrink-0 flex-col border-e border-line bg-paper
        px-3.5 pb-3.5 pt-5"
    >
      <div className="mb-3.5 flex items-center gap-2">
        <Logo className="h-6" />
        <div className="flex-1" />
        <LanguageToggle compact />
        <button
          type="button"
          onClick={onCollapse}
          aria-label={t('nav.collapse')}
          className="flex size-8 items-center justify-center rounded-lg text-ink-2
            transition hover:bg-paper-3 hover:text-ink"
        >
          <PanelCollapseIcon width={16} height={16} />
        </button>
      </div>

      <label className="relative mb-4 flex h-10 items-center gap-2 rounded-xl bg-paper-3 px-3">
        <SearchIcon width={15} height={15} className="shrink-0 text-ink-3" />
        <input
          ref={searchRef}
          type="search"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder={t('nav.searchChats')}
          className="min-w-0 flex-1 bg-transparent text-[13px] text-ink outline-none
            placeholder:text-ink-3"
        />
        {!query && (
          <kbd
            className="pointer-events-none hidden font-mono text-[11px] text-ink-3
              sm:inline [[data-touch]_&]:hidden"
          >
            ⌘K
          </kbd>
        )}
      </label>

      <div className="min-h-0 flex-1 space-y-[18px] overflow-y-auto">
        {filtered.length === 0 ? (
          <p className="px-2.5 text-xs text-ink-3">{t('nav.noResults')}</p>
        ) : (
          groups.map((group) => (
            <div key={group.key}>
              <p
                className="px-2.5 pb-1.5 text-[11px] font-semibold uppercase
                  tracking-[0.06em] text-ink-3 rtl:normal-case rtl:tracking-normal"
              >
                {groupLabel(group.key)}
              </p>
              <ul className="space-y-0.5">
                {group.items.map((conversation) => (
                  <ConversationRow
                    key={conversation.id}
                    id={conversation.id}
                    title={conversation.title}
                    onDelete={() => setPendingDeleteId(conversation.id)}
                  />
                ))}
              </ul>
            </div>
          ))
        )}
      </div>

      <ConfirmDialog
        open={pendingDeleteId !== null}
        title={t('chat.deleteTitle')}
        message={t('chat.deleteConfirm')}
        confirmLabel={t('chat.deleteChat')}
        danger
        busy={remove.isPending}
        onCancel={() => {
          if (!remove.isPending) setPendingDeleteId(null)
        }}
        onConfirm={() => void confirmDelete()}
      />
    </aside>
  )

  if (mobileOpen === undefined) {
    return panel
  }

  return (
    <>
      {mobileOpen && (
        <button
          type="button"
          aria-label={t('nav.collapse')}
          className="fixed inset-0 z-40 bg-glassy-overlay md:hidden"
          onClick={onMobileClose}
        />
      )}
      <div
        className={`fixed inset-y-0 start-0 z-50 transition-transform duration-200 md:static
          md:translate-x-0 ${
            mobileOpen ? 'translate-x-0' : '-translate-x-full rtl:translate-x-full md:rtl:translate-x-0'
          } ${mobileOpen === false ? 'md:hidden' : ''}`}
      >
        {panel}
      </div>
    </>
  )
}
