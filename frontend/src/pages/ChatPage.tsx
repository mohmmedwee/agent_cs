import { useEffect, useMemo, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useNavigate, useParams } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'

import { BlockView, isWrittenFileBlock } from '@/components/chat/Blocks'
import { ArtifactProvider, useArtifact } from '@/components/chat/ArtifactContext'
import { Composer } from '@/components/chat/Composer'
import {
  ArtifactPanel,
  DocumentFileCard,
  fileIdFromWriteResult,
  writeFilePayload,
} from '@/components/chat/DocumentPreview'
import { Logo } from '@/components/Logo'
import { ChevronIcon, EditIcon, SparkIcon, SpinnerIcon } from '@/components/Icons'
import { useChat } from '@/hooks/useChat'
import { useConversation, useCreateConversation } from '@/hooks/useConversations'
import { useLocalSetting } from '@/hooks/useLocalSetting'
import { api } from '@/lib/api'
import { skillDisplayName, toolDisplayName } from '@/lib/activityLabels'
import type { Block, Effort, StoredFile, StoredMessage, Turn } from '@/types'

/**
 * Stored messages come back as blocks. Turns written before blocks existed,
 * or ones that produced only prose, fall back to a single text block.
 */
function toTurns(messages: StoredMessage[]): Turn[] {
  return messages.map((message) =>
    message.role === 'user'
      ? { role: 'user', text: message.content }
      : {
          role: 'assistant',
          blocks: message.blocks ?? [{ kind: 'text', text: message.content }],
        },
  )
}

/** Marks where the agent's side of the conversation starts. */
function AgentAvatar() {
  const { t } = useTranslation()
  return (
    <div
      className="mt-0.5 flex size-8 shrink-0 items-center justify-center rounded-full
        bg-gradient-to-b from-primary-100 to-primary-25 text-primary
        ring-1 ring-primary-100 shadow-sm"
      title={t('chat.assistant')}
    >
      <SparkIcon width={16} height={16} />
    </div>
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
    if (block.name === 'web_search') return t('chat.searchedWeb')
    if (block.name === 'fetch_url') return t('chat.readPage')
    if (block.name === 'write_file') return t('chat.activityWroteFile')
    return toolDisplayName(block.name, t)
  }
  if (block.kind === 'error') return t('chat.activityError')
  return ''
}

/**
 * Finished tools collapse into one quiet row so the answer is the focus.
 * While anything is still running, the full trail stays open.
 */
function TurnActivity({
  blocks,
  turnComplete,
}: {
  blocks: Block[]
  turnComplete: boolean
}) {
  const { t } = useTranslation()
  const busy = blocks.some(progressIsActive)
  const [open, setOpen] = useState(true)

  useEffect(() => {
    if (busy) setOpen(true)
    else if (turnComplete) setOpen(false)
  }, [busy, turnComplete])

  if (blocks.length === 0) return null

  const labels = blocks
    .map((block) => activityLabel(block, t))
    .filter(Boolean)
  const summary =
    labels.length <= 3
      ? labels.join(' · ')
      : t('chat.activitySummaryCount', { count: labels.length })

  if (!open && !busy) {
    return (
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="inline-flex max-w-full items-center gap-1.5 rounded-full
          border border-secondary-200 bg-secondary-25/80 px-2.5 py-1
          text-[11px] font-medium text-secondary transition
          hover:border-secondary-300 hover:text-dark"
        aria-expanded={false}
      >
        <ChevronIcon
          width={12}
          height={12}
          className="shrink-0 rtl:-scale-x-100"
        />
        <span className="truncate">{summary || t('chat.activityShow')}</span>
      </button>
    )
  }

  return (
    <div className="space-y-1.5">
      {turnComplete && !busy ? (
        <button
          type="button"
          onClick={() => setOpen(false)}
          className="inline-flex items-center gap-1 text-[11px] font-medium
            text-secondary transition hover:text-dark"
          aria-expanded
        >
          <ChevronIcon
            width={12}
            height={12}
            className="rotate-90 rtl:-scale-x-100"
          />
          {t('chat.activityHide')}
        </button>
      ) : null}
      {blocks.map((block, blockIndex) => (
        <BlockView key={`p-${blockIndex}`} block={block} />
      ))}
    </div>
  )
}

/**
 * Answer first, then downloads, then thinking/tools underneath.
 * Users want to read the reply before the scratch work.
 */
function AssistantTurnBlocks({
  blocks,
  turnComplete,
}: {
  blocks: Block[]
  turnComplete: boolean
}) {
  const progress: Block[] = []
  const texts: Block[] = []
  const files: Extract<Block, { kind: 'tool' }>[] = []

  for (const block of blocks) {
    if (block.kind === 'text') texts.push(block)
    else if (isWrittenFileBlock(block)) files.push(block)
    else progress.push(block)
  }

  const hasAnswer = texts.some(
    (block) => block.kind === 'text' && block.text.trim().length > 0,
  )
  const showFiles = files.length > 0 && (hasAnswer || turnComplete)

  return (
    <>
      {hasAnswer ? (
        <div className="space-y-3">
          {texts.map((block, blockIndex) => (
            <BlockView key={`t-${blockIndex}`} block={block} />
          ))}
        </div>
      ) : (
        texts.map((block, blockIndex) => (
          <BlockView key={`t-${blockIndex}`} block={block} />
        ))
      )}

      {showFiles ? (
        <div className={hasAnswer ? 'mt-3 space-y-2.5' : 'space-y-2.5'}>
          {files.map((block, blockIndex) => {
            const fileId = fileIdFromWriteResult(block.result!)
            if (!fileId) return null
            const payload = writeFilePayload(block.args)
            return (
              <DocumentFileCard
                key={`f-${block.id}-${blockIndex}`}
                name={payload?.name || 'document'}
                fileId={fileId}
                content={payload?.content}
                autoOpen={turnComplete || hasAnswer}
              />
            )
          })}
        </div>
      ) : null}

      {progress.length > 0 ? (
        <div className={hasAnswer || showFiles ? 'mt-3' : undefined}>
          <TurnActivity blocks={progress} turnComplete={turnComplete} />
        </div>
      ) : null}
    </>
  )
}

function pendingWriteApproval(turns: Turn[]) {
  for (let i = turns.length - 1; i >= 0; i -= 1) {
    const turn = turns[i]
    if (turn.role !== 'assistant') continue
    for (const block of turn.blocks) {
      if (
        block.kind === 'tool' &&
        block.name === 'write_file' &&
        block.awaitingApproval
      ) {
        const payload = writeFilePayload(block.args)
        return {
          callId: block.id,
          fileName: payload?.name || 'document',
          pending: Boolean(block.approvalPending),
        }
      }
    }
  }
  return null
}

const STARTERS = [
  { labelKey: 'chat.starterSearchLabel', promptKey: 'chat.starterSearch' },
  { labelKey: 'chat.starterDocLabel', promptKey: 'chat.starterDoc' },
  { labelKey: 'chat.starterFileLabel', promptKey: 'chat.starterFile' },
  { labelKey: 'chat.starterCompareLabel', promptKey: 'chat.starterCompare' },
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
  const { closeArtifact } = useArtifact()

  const [model, setModel] = useLocalSetting<string | null>('model', null)
  const [effort, setEffort] = useLocalSetting<Effort>('effort', 'medium')
  const [uploading, setUploading] = useState(false)
  const [dragging, setDragging] = useState(false)
  const [editingIndex, setEditingIndex] = useState<number | null>(null)
  const [pendingAttachments, setPendingAttachments] = useState<StoredFile[]>([])

  const { data: conversation, isLoading } = useConversation(id)
  const create = useCreateConversation()
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

  useEffect(() => {
    if (id || create.isPending) return
    create.mutateAsync(undefined).then(
      (created) => navigate(`/chat/${created.id}`, { replace: true }),
      () => {},
    )
  }, [id, create, navigate])

  useEffect(() => {
    if (!conversation || busy) return
    setTurns(toTurns(conversation.messages))
  }, [conversation?.id, conversation?.messages.length]) // eslint-disable-line react-hooks/exhaustive-deps

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
  const title = conversation?.title?.trim()
  const editingTurn =
    editingIndex !== null && turns[editingIndex]?.role === 'user'
      ? turns[editingIndex]
      : null
  const approval = useMemo(() => pendingWriteApproval(turns), [turns])
  const { data: health } = useQuery({
    queryKey: ['health'],
    queryFn: () => api.health(),
    staleTime: 60_000,
  })
  const contextWindow = health?.context_window || 32_768

  const onComposerSend = (text: string) => {
    const message = withAttachments(text)
    setPendingAttachments([])
    if (editingIndex !== null && editingTurn?.role === 'user') {
      const index = editingIndex
      setEditingIndex(null)
      void editAndResend(index, message)
      return
    }
    send(message)
  }

  return (
    <div className="relative flex h-full min-h-0 overflow-hidden">
      <div
        className="relative flex h-full min-h-0 min-w-0 flex-1 flex-col overflow-hidden
          bg-gradient-to-b from-primary-50 via-primary-25/70 to-canvas"
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
              justify-center rounded-2xl border-2 border-dashed border-primary-300
              bg-primary-25/90 text-sm font-medium text-primary"
          >
            {t('chat.dropHere')}
          </div>
        )}

        {title && !empty && (
          <div
            className="sticky top-0 z-10 border-b border-primary-100/70 bg-glassy/80
              px-4 py-2.5 backdrop-blur-md"
          >
            <p className="mx-auto max-w-3xl truncate text-center text-sm font-medium text-dark">
              {title}
            </p>
          </div>
        )}

        <div
          ref={scroller}
          onScroll={onScroll}
          className="min-h-0 flex-1 overflow-y-auto overscroll-contain"
        >
          <div className="mx-auto max-w-3xl px-4 py-6 pb-2">
            {isLoading && empty && (
              <div className="flex justify-center py-16 text-secondary">
                <SpinnerIcon />
              </div>
            )}

            {!isLoading && empty && (
              <div className="animate-chat-in flex flex-col items-center px-2 py-14 text-center">
                <div
                  className="mb-6 flex size-16 items-center justify-center rounded-3xl
                    bg-surface shadow-md ring-1 ring-primary-100"
                >
                  <Logo className="h-7" />
                </div>
                <h2 className="text-2xl font-semibold tracking-tight text-dark">
                  {t('chat.emptyTitle')}
                </h2>
                <p className="mx-auto mt-2 max-w-md text-sm text-secondary">
                  {t('chat.emptyBody')}
                </p>
                <div className="mt-8 grid w-full max-w-xl gap-2 sm:grid-cols-2">
                  {STARTERS.map((starter) => (
                    <button
                      key={starter.labelKey}
                      type="button"
                      disabled={busy}
                      onClick={() => send(t(starter.promptKey))}
                      className="rounded-2xl border border-primary-100 bg-surface/90 px-4
                        py-3 text-start text-sm text-dark shadow-sm transition
                        hover:border-primary-300 hover:bg-primary-25 hover:shadow-md
                        disabled:opacity-50"
                    >
                      {t(starter.labelKey)}
                    </button>
                  ))}
                </div>
              </div>
            )}

            <div className="space-y-6">
              {turns.map((turn, index) =>
                turn.role === 'user' ? (
                  <div key={index} className="animate-chat-in flex justify-end">
                    <div className="group relative max-w-[85%]">
                      <div
                        className="whitespace-pre-wrap rounded-2xl rounded-ee-md
                          bg-gradient-to-b from-primary-400 to-primary px-4 py-2.5
                          text-sm text-white shadow-sm"
                        dir="auto"
                      >
                        {turn.text}
                      </div>
                      {!busy && (
                        <button
                          type="button"
                          onClick={() => setEditingIndex(index)}
                          aria-label={t('chat.editPrompt')}
                          className="absolute -start-10 top-1/2 flex size-8 -translate-y-1/2
                            items-center justify-center rounded-full border
                            border-secondary-200 bg-surface text-secondary opacity-0
                            shadow-sm transition hover:text-primary
                            group-hover:opacity-100 focus-visible:opacity-100"
                        >
                          <EditIcon width={14} height={14} />
                        </button>
                      )}
                    </div>
                  </div>
                ) : (
                  <div key={index} className="animate-chat-in flex gap-3">
                    <AgentAvatar />
                    <div className="min-w-0 flex-1 space-y-3">
                      <AssistantTurnBlocks
                        blocks={turn.blocks}
                        turnComplete={!busy || index !== turns.length - 1}
                      />
                      {busy &&
                        index === turns.length - 1 &&
                        !hasOwnProgress(turn.blocks) && (
                          <div className="flex items-center gap-2 text-xs text-secondary">
                            <SpinnerIcon width={14} height={14} />
                            <span>
                              {turn.blocks.length === 0
                                ? t('chat.thinking')
                                : t('chat.stillWorking')}
                            </span>
                          </div>
                        )}
                    </div>
                  </div>
                ),
              )}
            </div>
          </div>
        </div>

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
                  fileName: approval.fileName,
                  pending: approval.pending,
                  onAllow: () => void resolveApproval(approval.callId, true),
                  onDeny: () => void resolveApproval(approval.callId, false),
                }
              : null
          }
          session={{
            turns,
            busy,
            awaitingApproval: Boolean(approval),
            queueLength: queue.length,
            contextWindow,
            contextCompressed: Boolean(conversation?.context_compressed),
            contextSummary: conversation?.context_summary ?? null,
            summarizedCount: conversation?.summarized_count ?? 0,
          }}
          model={model}
          effort={effort}
          onModelChange={setModel}
          onEffortChange={setEffort}
        />
      </div>

      <ArtifactPanel />
    </div>
  )
}
