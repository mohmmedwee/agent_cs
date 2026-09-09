import { useCallback, useRef, useState } from 'react'
import type { Block, Turn } from '../types'
import { streamChat } from '../lib/sse'
import { toMessages } from '../lib/storage'

/** Skill loading is bookkeeping, not content — it gets a quiet chip. */
const SKILL_TOOL = 'read_skill'

function skillNameFrom(args: string): string {
  try {
    return String(JSON.parse(args).name ?? 'skill')
  } catch {
    return 'skill'
  }
}

type SetTurns = (update: Turn[] | ((previous: Turn[]) => Turn[])) => void

/**
 * Drives one request and folds the event stream into blocks on the last
 * assistant turn.
 */
export function useChat(turns: Turn[], setTurns: SetTurns) {
  const [busy, setBusy] = useState(false)
  const abort = useRef<AbortController | null>(null)
  const thoughtStartedAt = useRef(0)

  const patchBlocks = useCallback(
    (fn: (blocks: Block[]) => Block[]) => {
      setTurns((previous) => {
        const next = previous.slice()
        const last = next[next.length - 1]
        if (!last || last.role !== 'assistant') return previous
        next[next.length - 1] = { role: 'assistant', blocks: fn(last.blocks) }
        return next
      })
    },
    [setTurns],
  )

  /** Append to the trailing block when it matches, else start a new one. */
  const appendDelta = useCallback(
    (kind: 'text' | 'reasoning', text: string) => {
      patchBlocks((blocks) => {
        const last = blocks[blocks.length - 1]
        if (last?.kind === kind) {
          const merged = { ...last, text: last.text + text }
          return [...blocks.slice(0, -1), merged as Block]
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
      blocks.map((b) =>
        b.kind === 'reasoning' && b.open
          ? {
              ...b,
              open: false,
              seconds: Math.max(
                1,
                Math.round((Date.now() - thoughtStartedAt.current) / 1000),
              ),
            }
          : b,
      ),
    )
  }, [patchBlocks])

  const stop = useCallback(() => abort.current?.abort(), [])

  const send = useCallback(
    async (text: string) => {
      const trimmed = text.trim()
      if (!trimmed || abort.current) return

      const history = [...toMessages(turns), { role: 'user' as const, content: trimmed }]
      setTurns((previous) => [
        ...previous,
        { role: 'user', text: trimmed },
        { role: 'assistant', blocks: [] },
      ])

      const controller = new AbortController()
      abort.current = controller
      setBusy(true)

      try {
        for await (const event of streamChat(history, controller.signal)) {
          switch (event.type) {
            case 'text_delta':
              sealReasoning()
              appendDelta('text', event.text)
              break

            case 'reasoning_delta':
              appendDelta('reasoning', event.text)
              break

            case 'tool_call':
              sealReasoning()
              patchBlocks((blocks) => [
                ...blocks,
                event.name === SKILL_TOOL
                  ? {
                      kind: 'skill',
                      name: skillNameFrom(event.arguments),
                      loading: true,
                    }
                  : {
                      kind: 'tool',
                      id: event.id,
                      name: event.name,
                      args: event.arguments,
                    },
              ])
              break

            case 'tool_result':
              patchBlocks((blocks) =>
                blocks.map((b) => {
                  // The skill body is what we are deliberately not showing.
                  if (b.kind === 'skill' && b.loading) return { ...b, loading: false }
                  if (b.kind === 'tool' && b.id === event.id) {
                    return {
                      ...b,
                      result: event.result,
                      failed: event.result.startsWith('Error:'),
                    }
                  }
                  return b
                }),
              )
              break

            case 'error':
              sealReasoning()
              patchBlocks((blocks) => [...blocks, { kind: 'error', message: event.message }])
              break

            case 'done':
              break
          }
        }
      } catch (error) {
        const err = error as Error
        if (err.name !== 'AbortError') {
          patchBlocks((blocks) => [...blocks, { kind: 'error', message: err.message }])
        }
      } finally {
        sealReasoning()
        abort.current = null
        setBusy(false)
      }
    },
    [turns, setTurns, appendDelta, patchBlocks, sealReasoning],
  )

  return { send, stop, busy }
}
