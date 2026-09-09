import { useEffect, useMemo, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useNavigate, useParams } from 'react-router-dom'
import { useQueryClient } from '@tanstack/react-query'

import { BlockView } from '@/components/chat/Blocks'
import { Composer } from '@/components/chat/Composer'
import { SparkIcon, SpinnerIcon } from '@/components/Icons'
import { useChat } from '@/hooks/useChat'
import { useConversation, useCreateConversation } from '@/hooks/useConversations'
import { useLocalSetting } from '@/hooks/useLocalSetting'
import { api } from '@/lib/api'
import type { Block, Effort, StoredMessage, Turn } from '@/types'

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
        bg-primary-25 text-primary ring-1 ring-primary-100"
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
  if (last.kind === 'tool' && (last.streaming || last.result === undefined)) return true
  return false
}

export function ChatPage() {
  const { t } = useTranslation()
  const { id } = useParams()
  const navigate = useNavigate()
  const queryClient = useQueryClient()

  const [model] = useLocalSetting<string | null>('model', null)
  const [effort] = useLocalSetting<Effort>('effort', 'medium')
  const [uploading, setUploading] = useState(false)
  const [dragging, setDragging] = useState(false)

  const { data: conversation, isLoading } = useConversation(id)
  const create = useCreateConversation()
  const { turns, setTurns, send, stop, busy } = useChat({
    conversationId: id,
    model: model ?? undefined,
    effort,
  })

  // Landing on /chat with no id should not be a dead end; open a conversation.
  useEffect(() => {
    if (id || create.isPending) return
    create.mutateAsync(undefined).then(
      (created) => navigate(`/chat/${created.id}`, { replace: true }),
      () => {},
    )
  }, [id, create, navigate])

  // Load the stored transcript when opening a conversation. Not while a run is
  // in flight, or the server snapshot would overwrite live blocks.
  useEffect(() => {
    if (!conversation || busy) return
    setTurns(toTurns(conversation.messages))
  }, [conversation?.id, conversation?.messages.length]) // eslint-disable-line react-hooks/exhaustive-deps

  const scroller = useRef<HTMLDivElement>(null)
  const pinned = useRef(true)

  // Follow the stream, but stop following the moment the user scrolls up to
  // read something — yanking them back down is the worst part of chat UIs.
  const onScroll = () => {
    const node = scroller.current
    if (!node) return
    pinned.current = node.scrollHeight - node.scrollTop - node.clientHeight < 80
  }

  useEffect(() => {
    if (pinned.current) {
      scroller.current?.scrollTo({ top: scroller.current.scrollHeight })
    }
  }, [turns])

  const attach = async (files: File[]) => {
    setUploading(true)
    try {
      const stored = await api.files.upload(files)
      void queryClient.invalidateQueries({ queryKey: ['files'] })
      // Tell the agent what arrived; it decides whether to read them.
      send(
        `${t('chat.attachments', { count: stored.length })}: ${stored
          .map((file) => file.name)
          .join(', ')}`,
      )
    } finally {
      setUploading(false)
      setDragging(false)
    }
  }

  const empty = useMemo(() => turns.length === 0, [turns])

  return (
    <div
      className="relative flex h-full flex-col"
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

      <div ref={scroller} onScroll={onScroll} className="min-h-0 flex-1 overflow-y-auto">
        <div className="mx-auto max-w-3xl px-4 py-6">
          {isLoading && empty && (
            <div className="flex justify-center py-16 text-secondary">
              <SpinnerIcon />
            </div>
          )}

          {!isLoading && empty && (
            <div className="py-20 text-center">
              <h2 className="text-xl font-semibold text-dark">{t('chat.emptyTitle')}</h2>
              <p className="mx-auto mt-2 max-w-md text-sm text-secondary">
                {t('chat.emptyBody')}
              </p>
            </div>
          )}

          <div className="space-y-6">
            {turns.map((turn, index) =>
              turn.role === 'user' ? (
                <div key={index} className="flex justify-end">
                  <div
                    className="max-w-[85%] whitespace-pre-wrap rounded-2xl bg-primary
                      px-4 py-2.5 text-sm text-white"
                    dir="auto"
                  >
                    {turn.text}
                  </div>
                </div>
              ) : (
                <div key={index} className="flex gap-3">
                  <AgentAvatar />
                  <div className="min-w-0 flex-1 space-y-2.5">
                    {turn.blocks.map((block, blockIndex) => (
                      <BlockView key={blockIndex} block={block} />
                    ))}
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
        onSend={send}
        onStop={stop}
        onAttach={(files) => void attach(files)}
      />
    </div>
  )
}
