import { useCallback, useEffect, useRef, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'

import { streamChat } from '@/lib/sse'
import { conversationKeys } from '@/hooks/useConversations'
import type { Block, Effort, Turn } from '@/types'

/** Skill loading is bookkeeping, not content — it gets a quiet chip. */
const SKILL_TOOL = 'read_skill'

function skillNameFrom(args: string): string {
  try {
    return String(JSON.parse(args).name ?? 'skill')
  } catch {
    return 'skill'
  }
}

interface Options {
  conversationId: string | undefined
  model?: string
  effort?: Effort
}

/**
 * Drives one request and folds the event stream into blocks on the last
 * assistant turn.
 *
 * The transcript is kept in local state while streaming rather than refetched
 * per event; the server persists the same turn independently, so a reload
 * shows the identical result without the stream having to round-trip.
 */
export function useChat({ conversationId, model, effort }: Options) {
  const [turns, setTurns] = useState<Turn[]>([])
  const [busy, setBusy] = useState(false)
  const abort = useRef<AbortController | null>(null)
  const thoughtStartedAt = useRef(0)
  const queryClient = useQueryClient()

  // Switching conversations must cancel the run in flight, or its deltas land
  // in the newly opened transcript.
  useEffect(() => {
    return () => {
      abort.current?.abort()
      abort.current = null
    }
  }, [conversationId])

  const patchBlocks = useCallback((fn: (blocks: Block[]) => Block[]) => {
    setTurns((previous) => {
      const last = previous[previous.length - 1]
      if (!last || last.role !== 'assistant') return previous
      return [...previous.slice(0, -1), { role: 'assistant', blocks: fn(last.blocks) }]
    })
  }, [])

  /** Append to the trailing block when it matches, else start a new one. */
  const appendDelta = useCallback(
    (kind: 'text' | 'reasoning', text: string) => {
      patchBlocks((blocks) => {
        const last = blocks[blocks.length - 1]
        if (last?.kind === kind) {
          return [...blocks.slice(0, -1), { ...last, text: last.text + text } as Block]
        }
        if (kind === 'reasoning') {
          thoughtStartedAt.current = Date.now()
          return [...blocks, { kind: 'reasoning', text, seconds: 0, open: true }]
        }
        return [...blocks, { kind: 'text', text }]
      })
    },
    [patchBlocks],
  )

  /** Close any open reasoning block and stamp how long it ran. */
  const sealReasoning = useCallback(() => {
    patchBlocks((blocks) =>
      blocks.map((block) =>
        block.kind === 'reasoning' && block.open
          ? {
              ...block,
              open: false,
              seconds: Math.max(
                1,
                Math.round((Date.now() - thoughtStartedAt.current) / 1000),
              ),
            }
          : block,
      ),
    )
  }, [patchBlocks])

  const stop = useCallback(() => abort.current?.abort(), [])

  const send = useCallback(
    async (text: string) => {
      const trimmed = text.trim()
      if (!trimmed || abort.current || !conversationId) return

      setTurns((previous) => [
        ...previous,
        { role: 'user', text: trimmed },
        { role: 'assistant', blocks: [] },
      ])

      const controller = new AbortController()
      abort.current = controller
      setBusy(true)

      try {
        const stream = streamChat(
          { conversation_id: conversationId, message: trimmed, model, effort },
          controller.signal,
        )

        for await (const event of stream) {
          switch (event.type) {
            case 'text_delta':
              sealReasoning()
              appendDelta('text', event.text)
              break

            case 'reasoning_delta':
              appendDelta('reasoning', event.text)
              break

            case 'tool_call_delta':
              sealReasoning()
              patchBlocks((blocks) => {
                // Stable id while the real call id is still arriving: the model
                // streams the name and arguments long before the id is known.
                const pendingId = event.id || `pending-${event.index}`
                const existing = blocks.findIndex(
                  (block) =>
                    block.kind === 'tool' &&
                    (block.id === pendingId ||
                      block.id === `pending-${event.index}` ||
                      (block.streaming && block.name === event.name && event.name)),
                )
                const next = {
                  kind: 'tool' as const,
                  id: pendingId,
                  name: event.name || '…',
                  args: '',
                  streaming: true,
                  argumentsChars: event.arguments_chars,
                }
                if (existing >= 0) {
                  return [
                    ...blocks.slice(0, existing),
                    { ...blocks[existing], ...next },
                    ...blocks.slice(existing + 1),
                  ]
                }
                return [...blocks, next]
              })
              break

            case 'tool_call':
              sealReasoning()
              patchBlocks((blocks) => {
                if (event.name === SKILL_TOOL) {
                  // Drop any streaming placeholder for this skill, then chip.
                  const without = blocks.filter(
                    (block) =>
                      !(block.kind === 'tool' && block.streaming && block.name === SKILL_TOOL),
                  )
                  return [
                    ...without,
                    {
                      kind: 'skill',
                      name: skillNameFrom(event.arguments),
                      loading: true,
                    },
                  ]
                }
                const existing = blocks.findIndex(
                  (block) =>
                    block.kind === 'tool' &&
                    (block.id === event.id ||
                      (block.streaming &&
                        (block.name === event.name || block.name === '…'))),
                )
                const finished = {
                  kind: 'tool' as const,
                  id: event.id,
                  name: event.name,
                  args: event.arguments,
                  streaming: false,
                }
                if (existing >= 0) {
                  return [
                    ...blocks.slice(0, existing),
                    finished,
                    ...blocks.slice(existing + 1),
                  ]
                }
                return [...blocks, finished]
              })
              break

            case 'tool_result':
              patchBlocks((blocks) =>
                blocks.map((block) => {
                  // The skill body is what we are deliberately not showing.
                  if (block.kind === 'skill' && block.loading) {
                    return { ...block, loading: false }
                  }
                  if (block.kind === 'tool' && block.id === event.id) {
                    return {
                      ...block,
                      result: event.result,
                      failed: event.result.startsWith('Error:'),
                    }
                  }
                  return block
                }),
              )
              break

            case 'error':
              sealReasoning()
              patchBlocks((blocks) => [
                ...blocks,
                { kind: 'error', message: event.message },
              ])
              break

            case 'done':
              break
          }
        }
      } catch (error) {
        const problem = error as Error
        if (problem.name !== 'AbortError') {
          patchBlocks((blocks) => [
            ...blocks,
            { kind: 'error', message: problem.message },
          ])
        }
      } finally {
        sealReasoning()
        abort.current = null
        setBusy(false)
        // The first turn gives the conversation its title, and its updated_at
        // reorders the sidebar.
        void queryClient.invalidateQueries({ queryKey: conversationKeys.all })
      }
    },
    [
      conversationId,
      model,
      effort,
      appendDelta,
      patchBlocks,
      sealReasoning,
      queryClient,
    ],
  )

  return { turns, setTurns, send, stop, busy }
}
