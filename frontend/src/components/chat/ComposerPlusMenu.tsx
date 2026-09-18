import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'

import {
  BrainIcon,
  CheckIcon,
  ChevronIcon,
  FileIcon,
  GlobeIcon,
  PaperclipIcon,
  PlusIcon,
  SearchIcon,
  SparkIcon,
  SpinnerIcon,
} from '@/components/Icons'
import { api } from '@/lib/api'

type Panel = 'root' | 'skills'

export type ComposerTools = {
  webSearch: boolean
  research: boolean
  /** Active slash-skill token, e.g. "docx" shown as /docx */
  skill: string | null
}

interface Props {
  uploading: boolean
  disabled?: boolean
  tools: ComposerTools
  onToolsChange: (next: ComposerTools) => void
  onAttach: (files: File[]) => void
}

export function ComposerPlusMenu({
  uploading,
  disabled = false,
  tools,
  onToolsChange,
  onAttach,
}: Props) {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const [open, setOpen] = useState(false)
  const [panel, setPanel] = useState<Panel>('root')
  const root = useRef<HTMLDivElement>(null)
  const picker = useRef<HTMLInputElement>(null)

  const { data: skills = [], isLoading: skillsLoading } = useQuery({
    queryKey: ['skills'],
    queryFn: api.skills.list,
    enabled: open && panel === 'skills',
  })

  useEffect(() => {
    if (!open) return
    const onDoc = (event: MouseEvent) => {
      if (!root.current?.contains(event.target as Node)) {
        setOpen(false)
        setPanel('root')
      }
    }
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        setOpen(false)
        setPanel('root')
      }
    }
    document.addEventListener('mousedown', onDoc)
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('mousedown', onDoc)
      document.removeEventListener('keydown', onKey)
    }
  }, [open])

  const close = () => {
    setOpen(false)
    setPanel('root')
  }

  return (
    <div ref={root} className="relative">
      <input
        ref={picker}
        type="file"
        multiple
        accept="image/*,.pdf,.doc,.docx,.txt,.md,.csv,.xlsx,.pptx"
        hidden
        onChange={(event) => {
          const chosen = Array.from(event.target.files ?? [])
          if (chosen.length) onAttach(chosen)
          event.target.value = ''
          close()
        }}
      />

      <button
        type="button"
        disabled={disabled || uploading}
        aria-label={t('chat.plusMenu')}
        aria-expanded={open}
        aria-haspopup="menu"
        onClick={() => {
          setOpen((value) => !value)
          setPanel('root')
        }}
        className={[
          'inline-flex size-9 shrink-0 items-center justify-center rounded-xl',
          'border border-line text-ink-2 transition',
          'hover:border-primary/40 hover:bg-primary-25 hover:text-primary',
          'disabled:opacity-50',
          open ? 'border-primary/40 bg-primary-25 text-primary' : 'bg-surface',
        ].join(' ')}
      >
        {uploading ? (
          <SpinnerIcon width={18} height={18} />
        ) : (
          <PlusIcon width={18} height={18} />
        )}
      </button>

      {open ? (
        <div
          role="menu"
          className="absolute bottom-[calc(100%+0.5rem)] start-0 z-50 w-[17.5rem]
            overflow-hidden rounded-2xl border border-line bg-surface
            shadow-[var(--shadow-composer)]"
        >
          {panel === 'root' ? (
            <>
              <MenuSection>
                <MenuItem
                  icon={<PaperclipIcon width={16} height={16} />}
                  label={t('chat.plusAttach')}
                  hint="⌘U"
                  onClick={() => picker.current?.click()}
                />
                <MenuItem
                  icon={<FileIcon width={16} height={16} />}
                  label={t('chat.plusFiles')}
                  onClick={() => {
                    close()
                    navigate('/files')
                  }}
                />
              </MenuSection>

              <MenuDivider />

              <MenuSection>
                <MenuItem
                  icon={<SparkIcon width={16} height={16} />}
                  label={t('chat.plusSkills')}
                  chevron
                  onClick={() => setPanel('skills')}
                />
                <MenuItem
                  icon={<BrainIcon width={16} height={16} />}
                  label={t('chat.plusMemory')}
                  onClick={() => {
                    close()
                    navigate('/memory')
                  }}
                />
                <MenuItem
                  icon={<PlugIcon />}
                  label={t('chat.plusConnectors')}
                  chevron
                  disabled
                  hint={t('chat.plusSoon')}
                />
              </MenuSection>

              <MenuDivider />

              <MenuSection>
                <MenuItem
                  icon={<SearchIcon width={16} height={16} />}
                  label={t('chat.plusResearch')}
                  trailing={
                    tools.research ? (
                      <CheckIcon width={14} height={14} className="text-primary" />
                    ) : null
                  }
                  onClick={() =>
                    onToolsChange({ ...tools, research: !tools.research })
                  }
                />
                <MenuItem
                  icon={<GlobeIcon width={16} height={16} />}
                  label={t('chat.plusWebSearch')}
                  trailing={
                    tools.webSearch ? (
                      <CheckIcon width={14} height={14} className="text-primary" />
                    ) : null
                  }
                  onClick={() =>
                    onToolsChange({ ...tools, webSearch: !tools.webSearch })
                  }
                />
              </MenuSection>
            </>
          ) : (
            <>
              <div className="flex items-center gap-1 border-b border-line px-2 py-1.5">
                <button
                  type="button"
                  onClick={() => setPanel('root')}
                  className="rounded-lg px-2 py-1 text-xs font-medium text-ink-2
                    hover:bg-paper-3 hover:text-ink"
                >
                  ← {t('chat.plusBack')}
                </button>
                <span className="text-xs font-semibold text-ink">
                  {t('chat.plusSkills')}
                </span>
              </div>
              <MenuSection>
                <MenuItem
                  icon={<SparkIcon width={16} height={16} />}
                  label={t('chat.plusManageSkills')}
                  onClick={() => {
                    close()
                    navigate('/skills')
                  }}
                />
                <MenuItem
                  icon={<PlusIcon width={16} height={16} />}
                  label={t('chat.plusNewSkill')}
                  onClick={() => {
                    close()
                    navigate('/skills')
                  }}
                />
              </MenuSection>
              <MenuDivider />
              <div className="max-h-48 overflow-y-auto py-1">
                {skillsLoading ? (
                  <div className="flex justify-center py-4 text-ink-2">
                    <SpinnerIcon width={16} height={16} />
                  </div>
                ) : skills.length === 0 ? (
                  <p className="px-3 py-3 text-xs text-ink-2">
                    {t('chat.plusNoSkills')}
                  </p>
                ) : (
                  skills.slice(0, 12).map((skill) => (
                    <MenuItem
                      key={`${skill.source}-${skill.name}`}
                      icon={<SparkIcon width={14} height={14} />}
                      label={`/${skill.name}`}
                      hint={
                        skill.source === 'user'
                          ? t('skills.yours')
                          : t('skills.builtin')
                      }
                      trailing={
                        tools.skill === skill.name ? (
                          <CheckIcon
                            width={14}
                            height={14}
                            className="shrink-0 text-primary"
                          />
                        ) : undefined
                      }
                      onClick={() => {
                        onToolsChange({
                          ...tools,
                          skill:
                            tools.skill === skill.name ? null : skill.name,
                        })
                        close()
                      }}
                    />
                  ))
                )}
              </div>
            </>
          )}
        </div>
      ) : null}
    </div>
  )
}

function MenuSection({ children }: { children: React.ReactNode }) {
  return <div className="py-1">{children}</div>
}

function MenuDivider() {
  return <div className="border-t border-line" />
}

function MenuItem({
  icon,
  label,
  hint,
  chevron,
  trailing,
  disabled,
  onClick,
}: {
  icon: React.ReactNode
  label: string
  hint?: string
  chevron?: boolean
  trailing?: React.ReactNode
  disabled?: boolean
  onClick?: () => void
}) {
  return (
    <button
      type="button"
      role="menuitem"
      disabled={disabled}
      onClick={onClick}
      className="flex w-full items-center gap-2.5 px-3 py-2 text-start text-sm text-ink
        transition hover:bg-paper-3 disabled:cursor-not-allowed disabled:opacity-45"
    >
      <span
        className="inline-flex size-7 shrink-0 items-center justify-center
        rounded-lg bg-paper-3 text-ink-2"
      >
        {icon}
      </span>
      <span className="min-w-0 flex-1 truncate font-medium">{label}</span>
      {hint ? (
        <span className="shrink-0 text-[10px] font-medium uppercase tracking-wide text-ink-3">
          {hint}
        </span>
      ) : null}
      {trailing}
      {chevron ? (
        <ChevronIcon
          width={14}
          height={14}
          className="shrink-0 text-ink-3 rtl:rotate-180"
        />
      ) : null}
    </button>
  )
}

function PlugIcon() {
  return (
    <svg
      width={16}
      height={16}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.8}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden
    >
      <path d="M12 22v-5M9 8V2M15 8V2M8 8h8v4a4 4 0 0 1-8 0Z" />
    </svg>
  )
}
