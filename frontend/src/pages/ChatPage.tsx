import { useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { useNavigate, useOutletContext, useParams } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'

import { BlockView, isWrittenFileBlock } from '@/components/chat/Blocks'
import { ArtifactProvider, useArtifact } from '@/components/chat/ArtifactContext'
import { Composer } from '@/components/chat/Composer'
import { ChatSessionBar } from '@/components/chat/ChatSessionBar'
import {
  ArtifactPanel,
  DocumentFileList,
  filesFromToolResult,
  writeFilePayload,
  convertUploadPayload,
} from '@/components/chat/DocumentPreview'
import { ChoicePrompt, askUserPayload } from '@/components/chat/ChoicePrompt'
import { Logo } from '@/components/Logo'
import {
  BranchIcon,
  CheckIcon,
  ChevronIcon,
  CloseIcon,
  CompareIcon,
  CopyIcon,
  EditIcon,
  GlobeIcon,
  MenuIcon,
  PanelCollapseIcon,
  PaperclipIcon,
  PlusIcon,
  SpinnerIcon,
} from '@/components/Icons'
import { useChat } from '@/hooks/useChat'
import {
  useConversation,
  useConversations,
  useCreateConversation,
  useRenameConversation,
} from '@/hooks/useConversations'
import { useLocalSetting } from '@/hooks/useLocalSetting'
import { api } from '@/lib/api'
import { resumeChatRunIfActive } from '@/lib/chatRunner'
import { skillDisplayName, toolDisplayName } from '@/lib/activityLabels'
import type { Block, StoredFile, StoredMessage, Turn } from '@/types'
import { normalizeEffort } from '@/types'

function isProgressKind(block: Block): boolean {
  return block.kind === 'tool' || block.kind === 'skill' || block.kind === 'reasoning'
}

/** Highlight a leading `/skill-name` token the way the composer chip looks. */
function UserSlashText({ text }: { text: string }) {
  const match = text.match(/^(\/[a-z][a-z0-9-]*)(\s|$)/)
  if (!match) return <>{text}</>
  const token = match[1]
  const rest = text.slice(token.length)
  return (
    <>
      <span className="font-mono font-medium text-primary">{token}</span>
      {rest}
    </>
  )
}

/**
 * Interim narration sits in the trail; only text after the last tool/skill/
 * reasoning is the answer. While streaming, the newest text stays interim.
 */
function isInterimText(
  blocks: Block[],
  index: number,
  turnComplete: boolean,
): boolean {
  const block = blocks[index]
  if (!block || block.kind !== 'text') return false
  if (blocks.slice(index + 1).some(isProgressKind)) return true
  if (turnComplete) return false
  let lastText = -1
  for (let i = 0; i < blocks.length; i += 1) {
    if (blocks[i].kind === 'text') lastText = i
  }
  return index === lastText
}

function answerTextFromBlocks(blocks: Block[]): string {
  return blocks
    .filter(
      (block, index): block is Extract<Block, { kind: 'text' }> =>
        block.kind === 'text' && !isInterimText(blocks, index, true),
    )
    .map((block) => block.text)
    .join('\n\n')
    .trim()
}

const GATED_TOOLS = new Set(['write_file', 'convert_upload_to_docx'])

/**
 * Stored messages come back as blocks. Turns written before blocks existed,
 * or ones that produced only prose, fall back to a single text block.
 *
 * Tools saved without a result (job cancelled mid-approval) must not look
 * like a live wait — there is no Allow button for history.
 */
function toTurns(messages: StoredMessage[]): Turn[] {
  return messages.map((message) =>
    message.role === 'user'
      ? { role: 'user', text: message.content }
      : {
          role: 'assistant',
          blocks: (message.blocks ?? [{ kind: 'text', text: message.content }]).map(
            (block) => {
              if (
                block.kind === 'tool' &&
                block.result === undefined &&
                !block.streaming
              ) {
                return {
                  ...block,
                  result: 'Error: interrupted before this finished.',
                  failed: true,
                  awaitingApproval: false,
                  approvalPending: false,
                }
              }
              if (block.kind === 'skill' && block.loading) {
                return { ...block, loading: false }
              }
              if (block.kind === 'reasoning' && block.open) {
                return { ...block, open: false }
              }
              return block
            },
          ),
        },
  )
}


/**
 * True when the turn already shows its own progress UI, so a second
 * "still working" line would be noise — open reasoning, a skill loading, or a
 * tool waiting on its result.
 */
function hasOwnProgress(blocks: Block[]) {
  const last = blocks[blocks.length - 1]
  if (!last) return false
  if (last.kind === 'reasoning' && last.open) return true
  if (last.kind === 'skill' && last.loading) return true
  if (
    last.kind === 'tool' &&
    (last.streaming || last.awaitingApproval || last.result === undefined)
  ) {
    return true
  }
  return false
}

/**
 * True when a progress block is still mid-flight (keep the trail expanded).
 */
function progressIsActive(block: Block): boolean {
  if (block.kind === 'reasoning' && block.open) return true
  if (block.kind === 'skill' && block.loading) return true
  if (block.kind === 'tool') {
    return (
      block.streaming ||
      block.awaitingApproval ||
      block.result === undefined
    )
  }
  return false
}

function activityLabel(
  block: Block,
  t: (key: string, options?: Record<string, string | number>) => string,
): string {
  if (block.kind === 'reasoning') {
    return block.open ? t('chat.thinking') : t('chat.activityThought')
  }
  if (block.kind === 'skill') {
    const label = skillDisplayName(block.name, t)
    return block.loading
      ? `${t('chat.loadingSkill')}: ${label}`
      : `${t('chat.usedSkill')}: ${label}`
  }
  if (block.kind === 'tool') {
    if (block.name === 'web_search') return t('chat.webSearchDone')
    if (block.name === 'fetch_url') return t('chat.readPage')
    if (block.name === 'write_file') return t('chat.activityWroteFile')
    if (block.name === 'convert_upload_to_docx') return t('chat.activityConvertedDocx')
    if (block.name === 'run_python') return t('chat.activityRanPython')
    if (block.name === 'ask_user') return t('chat.toolAskUser')
    return toolDisplayName(block.name, t)
  }
  if (block.kind === 'error') return t('chat.activityError')
  return ''
}

/**
 * Quiet Workbench activity pill: collapsed summary with icons; expand for trail.
 */
function TurnActivity({
  blocks,
  turnComplete,
}: {
  blocks: Block[]
  turnComplete: boolean
}) {
  const { t } = useTranslation()
  const busy =
    blocks.some(progressIsActive) ||
    (!turnComplete && blocks.some((block) => block.kind === 'text'))
  const hasError = blocks.some((block) => block.kind === 'error')
  const [open, setOpen] = useState(false)
  const [prevBusy, setPrevBusy] = useState(busy)
  const trailRef = useRef<HTMLDivElement>(null)
  const stickToBottom = useRef(true)

  // Collapse once when a live run finishes — compare during render so we
  // avoid setState inside an effect (react(set-state-in-effect)).
  if (busy !== prevBusy) {
    setPrevBusy(busy)
    if (!busy) setOpen(false)
  }

  useEffect(() => {
    if (!open || !busy || !stickToBottom.current) return
    const node = trailRef.current
    if (!node) return
    node.scrollTop = node.scrollHeight
  }, [open, busy, blocks])

  if (blocks.length === 0) return null

  const labels = blocks
    .map((block) => activityLabel(block, t))
    .filter(Boolean)
  const liveLabel = labels[labels.length - 1] || t('chat.working')

  let summaryNodes: ReactNode
  if (busy) {
    summaryNodes = <span className="truncate">{liveLabel}</span>
  } else if (labels.length <= 3) {
    summaryNodes = (
      <span className="truncate">
        {labels.map((label, index) => (
          <span key={`${label}-${index}`}>
            {index > 0 && <span className="mx-1.5 text-line">·</span>}
            {label}
          </span>
        ))}
      </span>
    )
  } else {
    summaryNodes = (
      <span className="truncate">
        {labels[0]}
        <span className="mx-1.5 text-line">·</span>
        {labels[1]}
        <span className="mx-1.5 text-line">·</span>
        {t('chat.stepsSummary', { count: labels.length })}
      </span>
    )
  }

  const statusIcon = busy ? (
    <span className="flex size-[22px] shrink-0 items-center justify-center rounded-full bg-violet-tint text-primary">
      <SpinnerIcon width={13} height={13} />
    </span>
  ) : hasError ? (
    <span className="flex size-[22px] shrink-0 items-center justify-center rounded-full bg-error-50 text-error">
      <CloseIcon width={13} height={13} />
    </span>
  ) : (
    <span className="flex size-[22px] shrink-0 items-center justify-center rounded-full bg-success-50 text-success">
      <CheckIcon width={13} height={13} />
    </span>
  )

  return (
    <div>
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        aria-expanded={open}
        className="inline-flex max-w-full items-center gap-2.5 rounded-full border
          border-line bg-surface py-1.5 pe-3 ps-1.5 text-xs text-ink-2 transition
          hover:bg-paper-3"
      >
        {statusIcon}
        {summaryNodes}
        <ChevronIcon
          width={15}
          height={15}
          className={`ms-0.5 shrink-0 transition-transform ${
            open ? '-rotate-90' : 'rotate-90'
          }`}
        />
      </button>
      {open && (
        <div
          ref={trailRef}
          onScroll={() => {
            const node = trailRef.current
            if (!node) return
            stickToBottom.current =
              node.scrollHeight - node.scrollTop - node.clientHeight < 48
          }}
          className="mt-2 max-h-[360px] space-y-2 overflow-y-auto rounded-2xl border
            border-line bg-surface p-3"
        >
          {blocks.map((block, blockIndex) => (
            <BlockView
              key={`p-${blockIndex}`}
              block={block}
              compactText={block.kind === 'text'}
            />
          ))}
        </div>
      )}
    </div>
  )
}

/**
 * Activity pill first, then answer, then interactive choices, then downloads.
 */
function AssistantTurnBlocks({
  blocks,
  turnComplete,
  choicesInteractive = false,
  onChoice,
}: {
  blocks: Block[]
  turnComplete: boolean
  /** Latest finished turn: choice chips are clickable. */
  choicesInteractive?: boolean
  onChoice?: (option: string) => void
}) {
  const trail: Block[] = []
  const answers: Block[] = []
  const files: Extract<Block, { kind: 'tool' }>[] = []
  const choiceBlocks: Extract<Block, { kind: 'tool' }>[] = []

  blocks.forEach((block, index) => {
    if (block.kind === 'text') {
      if (isInterimText(blocks, index, turnComplete)) trail.push(block)
      else answers.push(block)
      return
    }
    if (block.kind === 'tool' && block.name === 'ask_user') {
      choiceBlocks.push(block)
      return
    }
    if (isWrittenFileBlock(block)) {
      files.push(block)
      return
    }
    trail.push(block)
  })

  const hasAnswer = answers.some(
    (block) => block.kind === 'text' && block.text.trim().length > 0,
  )
  const showFiles = files.length > 0 && (hasAnswer || turnComplete)

  const choiceCards = choiceBlocks
    .map((block) => askUserPayload(block.args, block.result))
    .filter((payload): payload is NonNullable<typeof payload> => Boolean(payload))

  return (
    <>
      {trail.length > 0 ? (
        <div>
          <TurnActivity blocks={trail} turnComplete={turnComplete} />
        </div>
      ) : null}

      <div
        className={`${trail.length > 0 ? 'mt-3' : ''} ${
          hasAnswer || !turnComplete ? 'min-h-[1.5rem]' : ''
        } space-y-3`}
      >
        {answers.map((block, blockIndex) => (
          <BlockView key={`t-${blockIndex}`} block={block} />
        ))}
      </div>

      {choiceCards.length > 0 ? (
        <div className={`${trail.length > 0 || hasAnswer ? 'mt-3' : ''} space-y-2`}>
          {choiceCards.map((card, index) => (
            <ChoicePrompt
              key={`choice-${index}-${card.question.slice(0, 24)}`}
              question={card.question}
              options={card.options}
              interactive={Boolean(choicesInteractive && onChoice)}
              onPick={(option) => onChoice?.(option)}
            />
          ))}
        </div>
      ) : null}

      {showFiles ? (
        <div className="mt-3">
          {(() => {
            const cards = files.flatMap((block) => {
              const payload =
                block.name === 'write_file'
                  ? writeFilePayload(block.args)
                  : block.name === 'convert_upload_to_docx'
                    ? convertUploadPayload(block.args)
                    : null
              return filesFromToolResult(block.result!).map((file) => ({
                blockId: block.id,
                name:
                  (payload && 'name' in payload ? payload.name : undefined) ||
                  (file.name !== 'document' ? file.name : undefined) ||
                  'document',
                fileId: file.id,
                content:
                  payload && 'content' in payload ? payload.content : undefined,
              }))
            })
            const rank = (name: string) => {
              const lower = name.toLowerCase()
              if (lower.endsWith('.docx')) return 0
              if (lower.endsWith('.xlsx')) return 1
              if (lower.endsWith('.pptx')) return 2
              if (/\.(png|jpe?g|gif|webp)$/i.test(lower)) return 3
              if (lower.endsWith('.json')) return 9
              return 5
            }
            const preferred =
              [...cards].sort((a, b) => rank(a.name) - rank(b.name))[0]?.fileId ??
              null
            const canOpen = turnComplete || hasAnswer
            return (
              <DocumentFileList
                files={cards.map((card) => ({
                  name: card.name,
                  fileId: card.fileId,
                  content: card.content,
                  autoOpen: canOpen && card.fileId === preferred,
                }))}
              />
            )
          })()}
        </div>
      ) : null}
    </>
  )
}

function TurnCopyButton({ text }: { text: string }) {
  const { t } = useTranslation()
  const [copied, setCopied] = useState(false)
  if (!text.trim()) return null

  return (
    <button
      type="button"
      onClick={() => {
        void navigator.clipboard.writeText(text).then(() => {
          setCopied(true)
          window.setTimeout(() => setCopied(false), 1600)
        })
      }}
      aria-label={copied ? t('chat.copied') : t('chat.copy')}
      title={copied ? t('chat.copied') : t('chat.copy')}
      className="inline-flex size-8 items-center justify-center rounded-lg text-ink-3
        transition hover:bg-paper-3 hover:text-ink"
    >
      {copied ? (
        <CheckIcon width={14} height={14} className="text-success" />
      ) : (
        <CopyIcon width={14} height={14} />
      )}
    </button>
  )
}

function pendingToolApproval(turns: Turn[], busy: boolean) {
  for (let i = turns.length - 1; i >= 0; i -= 1) {
    const turn = turns[i]
    if (turn.role !== 'assistant') continue
    for (const block of turn.blocks) {
      if (block.kind !== 'tool' || !GATED_TOOLS.has(block.name)) continue
      // Live run: gated tool with no result is waiting on Allow even if the
      // awaitingApproval flag was lost (refresh / stream drop).
      const needsAllow =
        block.awaitingApproval ||
        (busy &&
          block.result === undefined &&
          !block.streaming &&
          !block.approvalPending)
      if (!needsAllow) continue
      let fileName = 'document'
      if (block.name === 'write_file') {
        fileName = writeFilePayload(block.args)?.name || 'document'
      } else if (block.name === 'convert_upload_to_docx') {
        const payload = convertUploadPayload(block.args)
        fileName = payload?.name || payload?.source || 'document'
      }
      return {
        callId: block.id,
        toolName: block.name,
        fileName,
        pending: Boolean(block.approvalPending),
      }
    }
  }
  return null
}

const STARTERS = [
  {
    labelKey: 'chat.starterSearchLabel',
    promptKey: 'chat.starterSearch',
    Icon: GlobeIcon,
  },
  {
    labelKey: 'chat.starterDocLabel',
    promptKey: 'chat.starterDoc',
    Icon: EditIcon,
  },
  {
    labelKey: 'chat.starterFileLabel',
    promptKey: 'chat.starterFile',
    Icon: PaperclipIcon,
  },
  {
    labelKey: 'chat.starterCompareLabel',
    promptKey: 'chat.starterCompare',
    Icon: CompareIcon,
  },
] as const

export function ChatPage() {
  return (
    <ArtifactProvider>
      <ChatPageInner />
    </ArtifactProvider>
  )
}

function ChatPageInner() {
  const { t } = useTranslation()
  const { id } = useParams()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const { artifact, closeArtifact } = useArtifact()
  const outlet = useOutletContext<{
    conversationsCollapsed: boolean
    setConversationsCollapsed: (value: boolean) => void
    openMobileConversations: () => void
  }>()

  const [model, setModel] = useLocalSetting<string | null>('model', null)
  const [storedEffort, setEffort] = useLocalSetting<string>('effort', 'xhigh')
  const effort = normalizeEffort(storedEffort)
  const [uploading, setUploading] = useState(false)
  const [dragging, setDragging] = useState(false)
  const [editingIndex, setEditingIndex] = useState<number | null>(null)
  const [pendingAttachments, setPendingAttachments] = useState<StoredFile[]>([])
  const [renaming, setRenaming] = useState(false)
  const [renameDraft, setRenameDraft] = useState('')
  const rename = useRenameConversation()
  const create = useCreateConversation()

  const { data: conversation, isLoading } = useConversation(id)
  const { data: conversations, isSuccess: conversationsLoaded } = useConversations()
  const {
    turns,
    setTurns,
    send,
    stop,
    busy,
    queue,
    removeQueued,
    editAndResend,
    resolveApproval,
  } = useChat({
    conversationId: id,
    model: model ?? undefined,
    effort,
    title: conversation?.title,
  })

  // Bare /chat: open the latest conversation if any exist; otherwise stay empty
  // (do not auto-create — New chat is explicit).
  useEffect(() => {
    if (id || !conversationsLoaded) return
    const latest = conversations?.[0]
    if (latest) navigate(`/chat/${latest.id}`, { replace: true })
  }, [id, conversationsLoaded, conversations, navigate])

  useEffect(() => {
    if (!conversation || busy) return
    setTurns(toTurns(conversation.messages))
  }, [conversation?.id, conversation?.messages.length]) // eslint-disable-line react-hooks/exhaustive-deps

  // Full refresh wipes the in-memory runner; reattach if the server job is still live.
  useEffect(() => {
    if (!id || !conversation || busy) return
    void resumeChatRunIfActive({
      conversationId: id,
      priorTurns: toTurns(conversation.messages),
      title: conversation.title,
    })
  }, [id, conversation?.id]) // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    closeArtifact()
    setEditingIndex(null)
    setPendingAttachments([])
  }, [id]) // eslint-disable-line react-hooks/exhaustive-deps

  const scroller = useRef<HTMLDivElement>(null)
  const pinned = useRef(true)

  const onScroll = () => {
    const node = scroller.current
    if (!node) return
    pinned.current = node.scrollHeight - node.scrollTop - node.clientHeight < 80
  }

  useEffect(() => {
    if (pinned.current) {
      scroller.current?.scrollTo({ top: scroller.current.scrollHeight })
    }
  }, [turns, queue.length])

  const attach = async (files: File[]) => {
    setUploading(true)
    try {
      const stored = await api.files.upload(files)
      void queryClient.invalidateQueries({ queryKey: ['files'] })
      setPendingAttachments((previous) => {
        const seen = new Set(previous.map((file) => file.id))
        return [...previous, ...stored.filter((file) => !seen.has(file.id))]
      })
    } finally {
      setUploading(false)
      setDragging(false)
    }
  }

  const withAttachments = (text: string) => {
    const names = pendingAttachments.map((file) => file.name)
    if (names.length === 0) return text
    const note = t('chat.attachedFiles', { names: names.join(', ') })
    return text ? `${text}\n\n${note}` : note
  }

  const empty = useMemo(() => turns.length === 0, [turns])
  const threadMax = artifact ? 'max-w-[600px]' : 'max-w-[720px]'
  const editingTurn =
    editingIndex !== null && turns[editingIndex]?.role === 'user'
      ? turns[editingIndex]
      : null
  const approval = useMemo(() => pendingToolApproval(turns, busy), [turns, busy])
  const { data: health } = useQuery({
    queryKey: ['health'],
    queryFn: () => api.health(),
    staleTime: 60_000,
  })
  const contextWindow = health?.context_window || 32_768

  const saveRename = async () => {
    if (!id || !renameDraft.trim()) {
      setRenaming(false)
      return
    }
    try {
      await rename.mutateAsync({ id, title: renameDraft.trim() })
      setRenaming(false)
    } catch {
      // Keep editing on failure.
    }
  }

  const onComposerSend = (
    text: string,
    tools: { webSearch: boolean; research: boolean; skill: string | null } = {
      webSearch: true,
      research: false,
      skill: null,
    },
  ) => {
    const message = withAttachments(text)
    const trimmed = message.trim()
    // Chip already encoded into the message in Composer; don't double-prefix.
    const body = tools.skill
      ? trimmed.startsWith(`/${tools.skill}`)
        ? trimmed
        : trimmed
          ? `/${tools.skill} ${trimmed}`
          : `/${tools.skill}`
      : trimmed
    if (!body.trim()) return
    setPendingAttachments([])
    if (editingIndex !== null && editingTurn?.role === 'user') {
      const index = editingIndex
      setEditingIndex(null)
      void editAndResend(index, body, tools)
      return
    }
    send(body, tools)
  }

  return (
    <div className="relative flex h-full min-h-0 overflow-hidden">
      <div
        className="relative flex h-full min-h-0 min-w-0 flex-1 flex-col overflow-hidden bg-paper-2"
        onDragOver={(event) => {
          event.preventDefault()
          setDragging(true)
        }}
        onDragLeave={(event) => {
          if (!event.currentTarget.contains(event.relatedTarget as Node)) setDragging(false)
        }}
        onDrop={(event) => {
          event.preventDefault()
          const dropped = Array.from(event.dataTransfer.files)
          if (dropped.length) void attach(dropped)
          else setDragging(false)
        }}
      >
        {dragging && (
          <div
            className="pointer-events-none absolute inset-3 z-30 flex items-center
              justify-center rounded-2xl border-2 border-dashed border-line
              bg-surface/90 text-sm font-medium text-ink-2"
          >
            {t('chat.dropHere')}
          </div>
        )}

        <header
          className="flex h-[60px] shrink-0 items-center gap-3 border-b border-line-soft
            bg-paper-2 px-6"
        >
          {outlet?.conversationsCollapsed && (
            <button
              type="button"
              aria-label={t('nav.expand')}
              onClick={() => outlet.setConversationsCollapsed(false)}
              className="hidden size-9 items-center justify-center rounded-lg text-ink-2
                transition hover:bg-paper-3 hover:text-ink md:inline-flex"
            >
              <PanelCollapseIcon width={16} height={16} className="rtl:-scale-x-100" />
            </button>
          )}
          <button
            type="button"
            aria-label={t('nav.conversations')}
            className="inline-flex size-9 items-center justify-center rounded-lg text-ink-2
              transition hover:bg-paper-3 hover:text-ink md:hidden"
            onClick={() => outlet?.openMobileConversations()}
          >
            <MenuIcon width={18} height={18} />
          </button>

          <div className="flex min-w-0 flex-1 items-center gap-2">
            {renaming ? (
              <input
                autoFocus
                value={renameDraft}
                onChange={(event) => setRenameDraft(event.target.value)}
                onBlur={() => void saveRename()}
                onKeyDown={(event) => {
                  if (event.key === 'Enter') {
                    event.preventDefault()
                    void saveRename()
                  }
                  if (event.key === 'Escape') setRenaming(false)
                }}
                className="field max-w-md py-1.5 text-[15px] font-semibold"
                aria-label={t('chat.renameChat')}
              />
            ) : (
              <button
                type="button"
                onClick={() => {
                  setRenameDraft(conversation?.title ?? '')
                  setRenaming(true)
                }}
                className="inline-flex min-w-0 max-w-full items-center gap-1.5 rounded-lg
                  px-1.5 py-1 text-[15px] font-semibold text-ink transition hover:bg-paper-3"
              >
                <span className="truncate" dir="auto">
                  {conversation?.title || t('chat.emptyTitle')}
                </span>
                <ChevronIcon width={15} height={15} className="rotate-90 shrink-0 text-ink-3" />
              </button>
            )}
            {conversation?.parent_id ? (
              <span
                className="inline-flex h-[26px] shrink-0 items-center gap-1 rounded-full
                  bg-paper-3 px-2.5 text-xs text-ink-2"
              >
                <BranchIcon width={12} height={12} />
                {t('chat.branchBadge')}
              </span>
            ) : null}
          </div>

          <div className="hidden md:block">
            <ChatSessionBar
              turns={turns}
              busy={busy}
              awaitingApproval={Boolean(approval)}
              queueLength={queue.length}
              contextWindow={contextWindow}
              contextCompressed={Boolean(conversation?.context_compressed)}
              contextSummary={conversation?.context_summary ?? null}
              summarizedCount={conversation?.summarized_count ?? 0}
              placement="header"
            />
          </div>

          <button
            type="button"
            aria-label={t('nav.newChat')}
            className="inline-flex size-9 items-center justify-center rounded-lg text-ink-2
              transition hover:bg-paper-3 hover:text-ink md:hidden"
            onClick={() =>
              void create.mutateAsync(undefined).then((created) => navigate(`/chat/${created.id}`))
            }
          >
            <PlusIcon width={18} height={18} />
          </button>
        </header>

        {empty && !isLoading ? (
          <div className="flex min-h-0 flex-1 flex-col items-center justify-center px-4">
            <div className={`animate-chat-in flex w-full ${threadMax} flex-col items-center text-center`}>
              <Logo className="mb-6 h-7" />
              <h1 className="text-[28px] font-semibold tracking-tight text-ink">
                {t('chat.greeting')}
              </h1>
              <p className="mt-2 text-sm text-ink-2">{t('chat.emptyBody')}</p>
              <div className="mt-7 w-full">
                <Composer
                  busy={busy}
                  uploading={uploading}
                  queue={queue}
                  onSend={onComposerSend}
                  onStop={stop}
                  onAttach={(files) => void attach(files)}
                  onRemoveQueued={removeQueued}
                  pendingAttachments={pendingAttachments}
                  onRemoveAttachment={(fileId) =>
                    setPendingAttachments((previous) =>
                      previous.filter((file) => file.id !== fileId),
                    )
                  }
                  editing={null}
                  approval={null}
                  model={model}
                  effort={effort}
                  onModelChange={setModel}
                  onEffortChange={setEffort}
                  compact
                  emptyChat
                />
              </div>
              <div className="mt-5 grid w-full grid-cols-1 gap-2.5 sm:grid-cols-2">
                {STARTERS.map((starter) => (
                  <button
                    key={starter.labelKey}
                    type="button"
                    disabled={busy}
                    onClick={() => send(t(starter.promptKey))}
                    className="flex items-start gap-3 rounded-[14px] border border-line
                      bg-surface p-3.5 text-start transition hover:border-[#D6D1C7]
                      hover:bg-paper-2 disabled:opacity-50"
                  >
                    <span
                      className="flex size-8 shrink-0 items-center justify-center rounded-[10px]
                        bg-paper-3 text-ink-2"
                    >
                      <starter.Icon width={16} height={16} />
                    </span>
                    <span className="text-[13.5px] font-semibold text-ink">
                      {t(starter.labelKey)}
                    </span>
                  </button>
                ))}
              </div>
            </div>
          </div>
        ) : (
          <>
            <div
              ref={scroller}
              onScroll={onScroll}
              className="min-h-0 flex-1 overflow-y-auto overscroll-contain"
            >
              <div className={`mx-auto w-full ${threadMax} px-4 pb-2 pt-8`}>
                {isLoading && empty && (
                  <div className="flex justify-center py-16 text-ink-2">
                    <SpinnerIcon />
                  </div>
                )}

                <div className="space-y-7">
                  {turns.map((turn, index) =>
                    turn.role === 'user' ? (
                      <div key={index} className="animate-chat-in flex justify-end">
                        <div className="group relative max-w-[460px]">
                          <div
                            className="whitespace-pre-wrap rounded-[18px] rounded-ee-[6px]
                              bg-paper-3 px-4 py-3 text-[14.5px] leading-relaxed text-ink"
                            dir="auto"
                          >
                            <UserSlashText text={turn.text} />
                          </div>
                          {!busy && (
                            <button
                              type="button"
                              onClick={() => setEditingIndex(index)}
                              aria-label={t('chat.editPrompt')}
                              className="mt-1.5 inline-flex size-8 items-center justify-center
                                rounded-lg text-ink-3 opacity-0 transition hover:bg-paper-3
                                hover:text-ink group-hover:opacity-100 focus-visible:opacity-100"
                            >
                              <EditIcon width={14} height={14} />
                            </button>
                          )}
                        </div>
                      </div>
                    ) : (
                      <div key={index} className="group animate-chat-in min-w-0 space-y-3">
                        <AssistantTurnBlocks
                          blocks={turn.blocks}
                          turnComplete={!busy || index !== turns.length - 1}
                          choicesInteractive={index === turns.length - 1}
                          onChoice={(option) => onComposerSend(option)}
                        />
                        {busy &&
                          index === turns.length - 1 &&
                          !hasOwnProgress(turn.blocks) && (
                            <div className="flex items-center gap-2 text-xs text-ink-2">
                              <SpinnerIcon width={14} height={14} />
                              <span>
                                {turn.blocks.length === 0
                                  ? t('chat.thinking')
                                  : t('chat.stillWorking')}
                              </span>
                            </div>
                          )}
                        {!(busy && index === turns.length - 1) ? (
                          <div
                            className={`flex items-center gap-0.5 ${
                              index === turns.length - 1
                                ? ''
                                : 'opacity-0 transition group-hover:opacity-100 focus-within:opacity-100'
                            }`}
                          >
                            <TurnCopyButton text={answerTextFromBlocks(turn.blocks)} />
                          </div>
                        ) : null}
                      </div>
                    ),
                  )}
                </div>
              </div>
            </div>

            <div className={`mx-auto w-full ${threadMax} px-4 pb-4`}>
              <Composer
                busy={busy}
                uploading={uploading}
                queue={queue}
                onSend={onComposerSend}
                onStop={stop}
                onAttach={(files) => void attach(files)}
                onRemoveQueued={removeQueued}
                pendingAttachments={pendingAttachments}
                onRemoveAttachment={(fileId) =>
                  setPendingAttachments((previous) =>
                    previous.filter((file) => file.id !== fileId),
                  )
                }
                editing={
                  editingTurn && editingIndex !== null
                    ? {
                        text: editingTurn.text,
                        onCancel: () => setEditingIndex(null),
                      }
                    : null
                }
                approval={
                  approval
                    ? {
                        callId: approval.callId,
                        toolName: approval.toolName,
                        fileName: approval.fileName,
                        pending: approval.pending,
                        onAllow: () => void resolveApproval(approval.callId, true),
                        onDeny: () => void resolveApproval(approval.callId, false),
                      }
                    : null
                }
                model={model}
                effort={effort}
                onModelChange={setModel}
                onEffortChange={setEffort}
                emptyChat={false}
              />
            </div>
          </>
        )}
      </div>

      <ArtifactPanel turns={turns} />
    </div>
  )
}
