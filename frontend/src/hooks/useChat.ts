import { useCallback, useEffect, useMemo, useState, useSyncExternalStore } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'

import { api } from '@/lib/api'
import {
  bindChatRunner,
  enqueueChatMessage,
  getChatRun,
  patchChatRunBlocks,
  removeQueuedMessage,
  replaceChatRunTurns,
  setChatNotifyCopy,
  startChatRun,
  stopChatRun,
  subscribeChatRun,
} from '@/lib/chatRunner'
import { conversationKeys } from '@/hooks/useConversations'
import type { Effort, Turn } from '@/types'

interface Options {
  conversationId: string | undefined
  model?: string
  effort?: Effort
  title?: string
}

/**
 * Chat UI bound to a process-wide runner. Leaving the page does not abort —
 * only Stop does. Finished runs fire a browser notification when you are away.
 */
export function useChat({ conversationId, model, effort, title }: Options) {
  const queryClient = useQueryClient()
  const { t } = useTranslation()
  const [localTurns, setLocalTurns] = useState<Turn[]>([])

  useEffect(() => {
    bindChatRunner(queryClient)
  }, [queryClient])

  useEffect(() => {
    setChatNotifyCopy({
      title: t('chat.notifyDoneTitle'),
      body: t('chat.notifyDoneBody'),
    })
  }, [t])

  const runVersion = useSyncExternalStore(
    (listener) => subscribeChatRun(conversationId, listener),
    () => {
      const snap = getChatRun(conversationId)
      if (!snap) return 'idle'
      // Never JSON.stringify turns — xhigh reasoning made that allocate
      // multi‑MB strings on every token and crashed the tab.
      return `${snap.busy}:${snap.queue.length}:${snap.turns.length}:${snap.version}`
    },
    () => 'idle',
  )

  const active = useMemo(() => getChatRun(conversationId), [conversationId, runVersion])

  const turns = active?.turns ?? localTurns
  const busy = active?.busy ?? false
  const queue = active?.queue ?? []

  const setTurns = useCallback(
    (value: Turn[] | ((previous: Turn[]) => Turn[])) => {
      setLocalTurns((previous) => {
        // Never overwrite a live run with a server snapshot — that drops
        // awaitingApproval and hides Allow / Deny.
        if (active?.busy) return previous
        const basing = active?.turns ?? previous
        const next = typeof value === 'function' ? value(basing) : value
        if (active) replaceChatRunTurns(active.conversationId, next)
        return next
      })
    },
    [active],
  )

  // When opening a chat with no live run, mirror server turns into local state.
  // Active runs keep their own snapshot so navigate-away / navigate-back is seamless.
  useEffect(() => {
    if (active) return
    // localTurns are owned by ChatPage via setTurns(toTurns(...))
  }, [conversationId, active])

  const stop = useCallback(() => stopChatRun(conversationId), [conversationId])

  const removeQueued = useCallback(
    (index: number) => {
      if (conversationId) removeQueuedMessage(conversationId, index)
    },
    [conversationId],
  )

  const send = useCallback(
    (text: string) => {
      const trimmed = text.trim()
      if (!trimmed || !conversationId) return

      if (busy) {
        enqueueChatMessage(conversationId, trimmed)
        return
      }

      startChatRun({
        conversationId,
        message: trimmed,
        priorTurns: turns,
        model,
        effort,
        title,
      })
    },
    [busy, conversationId, turns, model, effort, title],
  )

  const editAndResend = useCallback(
    async (turnIndex: number, text: string) => {
      const trimmed = text.trim()
      if (!trimmed || !conversationId || busy) return

      const turn = turns[turnIndex]
      if (!turn || turn.role !== 'user') return

      stopChatRun(conversationId)
      await api.conversations.rewind(conversationId, turnIndex)
      const prior = turns.slice(0, turnIndex)
      setLocalTurns(prior)
      void queryClient.invalidateQueries({
        queryKey: conversationKeys.detail(conversationId),
      })
      startChatRun({
        conversationId,
        message: trimmed,
        priorTurns: prior,
        model,
        effort,
        title,
      })
    },
    [conversationId, turns, busy, model, effort, title, queryClient],
  )

  const resolveApproval = useCallback(
    async (callId: string, allowed: boolean) => {
      if (!conversationId) return
      patchChatRunBlocks(conversationId, (blocks) =>
        blocks.map((block) =>
          block.kind === 'tool' && block.id === callId
            ? { ...block, awaitingApproval: false, approvalPending: true }
            : block,
        ),
      )
      // Keep local mirror in sync when run already finished (shouldn't happen).
      setLocalTurns((previous) => {
        const last = previous[previous.length - 1]
        if (!last || last.role !== 'assistant') return previous
        return [
          ...previous.slice(0, -1),
          {
            role: 'assistant',
            blocks: last.blocks.map((block) =>
              block.kind === 'tool' && block.id === callId
                ? { ...block, awaitingApproval: false, approvalPending: true }
                : block,
            ),
          },
        ]
      })
      try {
        await api.chat.approve({
          conversation_id: conversationId,
          call_id: callId,
          allowed,
        })
      } catch (error) {
        patchChatRunBlocks(conversationId, (blocks) =>
          blocks.map((block) =>
            block.kind === 'tool' && block.id === callId
              ? { ...block, awaitingApproval: true, approvalPending: false }
              : block,
          ),
        )
        throw error
      }
    },
    [conversationId],
  )

  return {
    turns,
    setTurns,
    send,
    stop,
    busy,
    queue,
    removeQueued,
    editAndResend,
    resolveApproval,
  }
}
