import type { QueryClient } from '@tanstack/react-query'

import { api, ApiError } from '@/lib/api'
import { conversationKeys } from '@/hooks/useConversations'
import { streamChat, watchChat } from '@/lib/sse'
import { ensureNotifyPermission, notifyChatDone } from '@/lib/notify'
import { isRunawayRepetition, trimRunawayTail } from '@/lib/runaway'
import type { AgentEvent, Block, Effort, Turn } from '@/types'

const SKILL_TOOL = 'read_skill'

function skillNameFrom(args: string): string {
  try {
    return String(JSON.parse(args).name ?? 'skill')
  } catch {
    return 'skill'
  }
}

export interface ChatRunSnapshot {
  conversationId: string
  turns: Turn[]
  busy: boolean
  queue: string[]
  title: string
  /** Monotonic UI revision — prefer this over stringifying turns. */
  version: number
}

type Listener = () => void

interface ActiveRun {
  conversationId: string
  title: string
  turns: Turn[]
  queue: string[]
  busy: boolean
  controller: AbortController
  thoughtStartedAt: number
  listeners: Set<Listener>
  version: number
  emitRaf: number
}

/** Survives ChatPage unmount so leaving a chat does not abort the stream. */
const runs = new Map<string, ActiveRun>()

/** Cap UI-held strings so xhigh thinking / giant tool args cannot OOM the tab. */
const REASONING_UI_CAP = 12_000
const TOOL_ARGS_UI_CAP = 16_000
const TOOL_RESULT_UI_CAP = 24_000

function clipUi(text: string, cap: number): string {
  if (text.length <= cap) return text
  return `${text.slice(0, cap)}\n…[truncated for display]`
}
let queryClient: QueryClient | null = null
let notifyCopy: { title: string; body: string } = {
  title: 'cleverso-ai',
  body: 'Your reply is ready.',
}

export function bindChatRunner(client: QueryClient): void {
  queryClient = client
}

export function setChatNotifyCopy(copy: { title: string; body: string }): void {
  notifyCopy = copy
}

export function getChatRun(conversationId: string | undefined): ChatRunSnapshot | null {
  if (!conversationId) return null
  const run = runs.get(conversationId)
  if (!run) return null
  return {
    conversationId: run.conversationId,
    turns: run.turns,
    busy: run.busy,
    queue: run.queue,
    title: run.title,
    version: run.version,
  }
}

export function isChatBusy(conversationId: string | undefined): boolean {
  if (!conversationId) return false
  return Boolean(runs.get(conversationId)?.busy)
}

export function subscribeChatRun(
  conversationId: string | undefined,
  listener: Listener,
): () => void {
  if (!conversationId) return () => {}
  let run = runs.get(conversationId)
  if (!run) {
    // Listener waits until a run starts for this id.
    const pending: Listener = listener
    const wrapper: Listener = () => pending()
    // Store on a side map of waiters
    waiters.get(conversationId)?.add(wrapper) ??
      waiters.set(conversationId, new Set([wrapper]))
    return () => {
      waiters.get(conversationId)?.delete(wrapper)
    }
  }
  run.listeners.add(listener)
  return () => {
    run?.listeners.delete(listener)
  }
}

const waiters = new Map<string, Set<Listener>>()

function flushEmit(run: ActiveRun): void {
  for (const listener of run.listeners) listener()
  const pending = waiters.get(run.conversationId)
  if (pending) {
    for (const listener of pending) listener()
  }
}

function emit(run: ActiveRun, urgent = false): void {
  run.version += 1
  if (urgent) {
    if (run.emitRaf) {
      cancelAnimationFrame(run.emitRaf)
      run.emitRaf = 0
    }
    flushEmit(run)
    return
  }
  // Coalesce high-frequency reasoning/text deltas to one paint per frame.
  if (run.emitRaf) return
  run.emitRaf = requestAnimationFrame(() => {
    run.emitRaf = 0
    flushEmit(run)
  })
}

function patchBlocks(run: ActiveRun, fn: (blocks: Block[]) => Block[]): void {
  const last = run.turns[run.turns.length - 1]
  if (!last || last.role !== 'assistant') return
  run.turns = [
    ...run.turns.slice(0, -1),
    { role: 'assistant', blocks: fn(last.blocks) },
  ]
}

function appendDelta(run: ActiveRun, kind: 'text' | 'reasoning', text: string): void {
  patchBlocks(run, (blocks) => {
    const last = blocks[blocks.length - 1]
    if (last?.kind === kind) {
      if (kind === 'reasoning' && last.text.length >= REASONING_UI_CAP) {
        return blocks
      }
      let nextText = last.text + text
      if (kind === 'text' && isRunawayRepetition(nextText)) {
        nextText = trimRunawayTail(nextText)
      }
      if (kind === 'reasoning') {
        nextText = clipUi(nextText, REASONING_UI_CAP)
      }
      return [...blocks.slice(0, -1), { ...last, text: nextText } as Block]
    }
    if (kind === 'reasoning') {
      run.thoughtStartedAt = Date.now()
      return [
        ...blocks,
        { kind: 'reasoning', text: clipUi(text, REASONING_UI_CAP), seconds: 0, open: true },
      ]
    }
    const initial = kind === 'text' && isRunawayRepetition(text) ? trimRunawayTail(text) : text
    return [...blocks, { kind: 'text', text: initial }]
  })
}

function sealReasoning(run: ActiveRun): void {
  patchBlocks(run, (blocks) =>
    blocks.map((block) =>
      block.kind === 'reasoning' && block.open
        ? {
            ...block,
            open: false,
            seconds: Math.max(1, Math.round((Date.now() - run.thoughtStartedAt) / 1000)),
          }
        : block,
    ),
  )
}

function applyEvent(run: ActiveRun, event: AgentEvent): void {
  switch (event.type) {
    case 'text_delta':
      sealReasoning(run)
      appendDelta(run, 'text', event.text)
      break
    case 'reasoning_delta':
      appendDelta(run, 'reasoning', event.text)
      break
    case 'tool_call_delta':
      sealReasoning(run)
      patchBlocks(run, (blocks) => {
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
      sealReasoning(run)
      patchBlocks(run, (blocks) => {
        if (event.name === SKILL_TOOL) {
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
              (block.streaming && (block.name === event.name || block.name === '…'))),
        )
        const finished = {
          kind: 'tool' as const,
          id: event.id,
          name: event.name,
          args: clipUi(event.arguments, TOOL_ARGS_UI_CAP),
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
    case 'tool_approval':
      sealReasoning(run)
      patchBlocks(run, (blocks) => {
        const existing = blocks.findIndex(
          (block) => block.kind === 'tool' && block.id === event.id,
        )
        if (existing >= 0) {
          const block = blocks[existing]
          if (block.kind !== 'tool') return blocks
          return [
            ...blocks.slice(0, existing),
            {
              ...block,
              name: event.name || block.name,
              args: event.arguments
                ? clipUi(event.arguments, TOOL_ARGS_UI_CAP)
                : block.args,
              streaming: false,
              awaitingApproval: true,
              approvalPending: false,
            },
            ...blocks.slice(existing + 1),
          ]
        }
        // tool_call may have been missed (partial replay) — still show Allow.
        return [
          ...blocks,
          {
            kind: 'tool' as const,
            id: event.id,
            name: event.name,
            args: clipUi(event.arguments, TOOL_ARGS_UI_CAP),
            streaming: false,
            awaitingApproval: true,
          },
        ]
      })
      break
    case 'tool_result':
      patchBlocks(run, (blocks) =>
        blocks.map((block) => {
          if (block.kind === 'skill' && block.loading) {
            return { ...block, loading: false }
          }
          if (block.kind === 'tool' && block.id === event.id) {
            if (
              (event.name === 'write_file' ||
                event.name === 'run_python' ||
                event.name === 'convert_upload_to_docx') &&
              !event.result.startsWith('Error:')
            ) {
              void queryClient?.invalidateQueries({ queryKey: ['files'] })
            }
            return {
              ...block,
              result: clipUi(event.result, TOOL_RESULT_UI_CAP),
              failed: event.result.startsWith('Error:'),
              awaitingApproval: false,
              approvalPending: false,
            }
          }
          return block
        }),
      )
      break
    case 'error':
      sealReasoning(run)
      patchBlocks(run, (blocks) => [...blocks, { kind: 'error', message: event.message }])
      break
    case 'done':
      break
  }
}

async function pump(run: ActiveRun, message: string, model?: string, effort?: Effort): Promise<void> {
  let aborted = false
  try {
    const stream = streamChat(
      { conversation_id: run.conversationId, message, model, effort },
      run.controller.signal,
    )
    for await (const event of stream) {
      applyEvent(run, event)
      emit(run)
    }
  } catch (error) {
    const problem = error as Error
    aborted = problem.name === 'AbortError' || run.controller.signal.aborted
    if (!aborted) {
      sealReasoning(run)
      patchBlocks(run, (blocks) => [
        ...blocks,
        { kind: 'error', message: problem.message },
      ])
      emit(run, true)
    }
  } finally {
    aborted = aborted || run.controller.signal.aborted
    if (!aborted) {
      // Original POST stream ended (proxy idle / refresh). Job may still be
      // waiting on Allow — keep the runner alive via /chat/watch.
      const kept = await watchUntilJobEnds(run)
      if (kept) return
    }
    await finishRun(run, { aborted, model, effort })
  }
}

/**
 * Reattach to the server job until it finishes or the user hits Stop.
 * Returns true if this call owned teardown (caller must not finish again).
 */
async function watchUntilJobEnds(run: ActiveRun): Promise<boolean> {
  for (let attempt = 0; attempt < 8; attempt += 1) {
    if (run.controller.signal.aborted) return false
    try {
      const { active } = await api.chat.active(run.conversationId)
      if (!active) return false
    } catch {
      return false
    }

    run.busy = true
    run.controller = new AbortController()
    emit(run, true)

    let aborted = false
    try {
      for await (const event of watchChat(run.conversationId, run.controller.signal)) {
        applyEvent(run, event)
        emit(run)
      }
    } catch (error) {
      const problem = error as Error
      aborted = problem.name === 'AbortError' || run.controller.signal.aborted
      if (!aborted && (error as ApiError).status !== 404) {
        sealReasoning(run)
        patchBlocks(run, (blocks) => [
          ...blocks,
          { kind: 'error', message: problem.message },
        ])
        emit(run, true)
      }
      if (aborted || (error as ApiError).status === 404) {
        await finishRun(run, { aborted })
        return true
      }
    }
    // Stream ended without abort — loop and check active again.
  }
  await finishRun(run, { aborted: false })
  return true
}

async function finishRun(
  run: ActiveRun,
  options: { aborted: boolean; model?: string; effort?: Effort },
): Promise<void> {
  const { aborted, model, effort } = options
  sealReasoning(run)
  run.busy = false
  emit(run, true)

  void queryClient?.invalidateQueries({ queryKey: conversationKeys.all })
  void queryClient?.invalidateQueries({
    queryKey: conversationKeys.detail(run.conversationId),
  })

  if (!aborted) {
    notifyChatDone({
      conversationId: run.conversationId,
      title: notifyCopy.title,
      body: notifyCopy.body.replace('{{title}}', run.title),
    })
  }

  const next = run.queue[0]
  if (next && !aborted) {
    run.queue = run.queue.slice(1)
    run.turns = [
      ...run.turns,
      { role: 'user', text: next },
      { role: 'assistant', blocks: [] },
    ]
    run.busy = true
    run.controller = new AbortController()
    emit(run, true)
    await pump(run, next, model, effort)
    return
  }

  runs.delete(run.conversationId)
  emit(run, true)
  waiters.delete(run.conversationId)
}

export function startChatRun(options: {
  conversationId: string
  message: string
  priorTurns: Turn[]
  model?: string
  effort?: Effort
  title?: string
}): void {
  const existing = runs.get(options.conversationId)
  if (existing?.busy) {
    existing.queue = [...existing.queue, options.message]
    emit(existing, true)
    return
  }

  void ensureNotifyPermission()

  const controller = new AbortController()
  const run: ActiveRun = {
    conversationId: options.conversationId,
    title: options.title?.trim() || 'Chat',
    turns: [
      ...options.priorTurns,
      { role: 'user', text: options.message },
      { role: 'assistant', blocks: [] },
    ],
    queue: [],
    busy: true,
    controller,
    thoughtStartedAt: 0,
    listeners: new Set(waiters.get(options.conversationId) ?? []),
    version: 0,
    emitRaf: 0,
  }
  waiters.delete(options.conversationId)
  runs.set(options.conversationId, run)
  emit(run, true)
  void pump(run, options.message, options.model, options.effort)
}

export function stopChatRun(conversationId: string | undefined): void {
  if (!conversationId) return
  const run = runs.get(conversationId)
  if (!run) return
  run.queue = []
  run.controller.abort()
  // Server job keeps running after a plain fetch abort — cancel it explicitly.
  void api.chat.stop(conversationId).catch(() => {})
}

/**
 * After a full page refresh the in-memory runner is gone but the server job
 * may still be generating. Reattach so the UI streams again without Stop.
 */
export async function resumeChatRunIfActive(options: {
  conversationId: string
  priorTurns: Turn[]
  title?: string
}): Promise<boolean> {
  if (runs.get(options.conversationId)?.busy) return true
  try {
    const { active } = await api.chat.active(options.conversationId)
    if (!active) return false
  } catch {
    return false
  }

  const controller = new AbortController()
  const run: ActiveRun = {
    conversationId: options.conversationId,
    title: options.title?.trim() || 'Chat',
    turns: [
      ...options.priorTurns,
      { role: 'assistant', blocks: [] },
    ],
    queue: [],
    busy: true,
    controller,
    thoughtStartedAt: 0,
    listeners: new Set(waiters.get(options.conversationId) ?? []),
    version: 0,
    emitRaf: 0,
  }
  waiters.delete(options.conversationId)
  runs.set(options.conversationId, run)
  emit(run, true)

  void (async () => {
    let aborted = false
    try {
      for await (const event of watchChat(options.conversationId, controller.signal)) {
        applyEvent(run, event)
        emit(run)
      }
    } catch (error) {
      const problem = error as Error
      aborted = problem.name === 'AbortError' || controller.signal.aborted
      if (!aborted && (error as ApiError).status !== 404) {
        sealReasoning(run)
        patchBlocks(run, (blocks) => [
          ...blocks,
          { kind: 'error', message: problem.message },
        ])
        emit(run, true)
      }
    } finally {
      if (!aborted) {
        const kept = await watchUntilJobEnds(run)
        if (kept) return
      }
      await finishRun(run, { aborted })
    }
  })()

  return true
}

export function enqueueChatMessage(conversationId: string, message: string): boolean {
  const run = runs.get(conversationId)
  if (!run?.busy) return false
  run.queue = [...run.queue, message]
  emit(run, true)
  return true
}

export function removeQueuedMessage(conversationId: string, index: number): void {
  const run = runs.get(conversationId)
  if (!run) return
  run.queue = run.queue.filter((_, i) => i !== index)
  emit(run, true)
}

export function replaceChatRunTurns(conversationId: string, turns: Turn[]): void {
  const run = runs.get(conversationId)
  if (!run) return
  run.turns = turns
  emit(run, true)
}

export function patchChatRunBlocks(
  conversationId: string,
  fn: (blocks: Block[]) => Block[],
): void {
  const run = runs.get(conversationId)
  if (!run) return
  patchBlocks(run, fn)
  emit(run, true)
}
