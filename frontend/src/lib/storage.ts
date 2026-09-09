import type { Block, Session, Turn } from '../types'
import type { ChatMessage } from './sse'

const KEY = 'agent-console.sessions.v1'
const ACTIVE = 'agent-console.active.v1'

/** Tool output can be tens of thousands of characters; localStorage cannot. */
const STORED_RESULT_LIMIT = 2_000
const MAX_SESSIONS = 50

export const newId = () =>
  `${Date.now().toString(36)}${Math.random().toString(36).slice(2, 8)}`

export function emptySession(): Session {
  const now = Date.now()
  return { id: newId(), title: 'New chat', createdAt: now, updatedAt: now, turns: [] }
}

/** First user message, trimmed to something that fits the sidebar. */
export function titleFor(turns: Turn[]): string {
  const first = turns.find((t) => t.role === 'user')
  if (!first || first.role !== 'user') return 'New chat'
  const line = first.text.trim().split('\n')[0]
  return line.length > 42 ? `${line.slice(0, 42)}…` : line || 'New chat'
}

/** What we replay to the server: prose only, no tool or reasoning blocks. */
export function toMessages(turns: Turn[]): ChatMessage[] {
  const messages: ChatMessage[] = []
  for (const turn of turns) {
    if (turn.role === 'user') {
      messages.push({ role: 'user', content: turn.text })
      continue
    }
    const text = turn.blocks
      .filter((b): b is Extract<Block, { kind: 'text' }> => b.kind === 'text')
      .map((b) => b.text)
      .join('')
      .trim()
    if (text) messages.push({ role: 'assistant', content: text })
  }
  return messages
}

function shrink(session: Session): Session {
  return {
    ...session,
    turns: session.turns.map((turn) =>
      turn.role === 'assistant'
        ? {
            ...turn,
            blocks: turn.blocks.map((b) =>
              b.kind === 'tool' && b.result && b.result.length > STORED_RESULT_LIMIT
                ? { ...b, result: `${b.result.slice(0, STORED_RESULT_LIMIT)}\n\n[trimmed]` }
                : b,
            ),
          }
        : turn,
    ),
  }
}

export function loadSessions(): Session[] {
  try {
    const raw = localStorage.getItem(KEY)
    if (!raw) return []
    const parsed = JSON.parse(raw)
    return Array.isArray(parsed) ? (parsed as Session[]) : []
  } catch {
    return []
  }
}

export function saveSessions(sessions: Session[]): void {
  const trimmed = sessions
    .slice()
    .sort((a, b) => b.updatedAt - a.updatedAt)
    .slice(0, MAX_SESSIONS)
    .map(shrink)
  try {
    localStorage.setItem(KEY, JSON.stringify(trimmed))
  } catch {
    // Quota exceeded: keep only the most recent few rather than losing all.
    try {
      localStorage.setItem(KEY, JSON.stringify(trimmed.slice(0, 5)))
    } catch {
      /* give up silently; the session still works in memory */
    }
  }
}

export const loadActiveId = () => localStorage.getItem(ACTIVE)
export const saveActiveId = (id: string) => {
  try {
    localStorage.setItem(ACTIVE, id)
  } catch {
    /* non-fatal */
  }
}
