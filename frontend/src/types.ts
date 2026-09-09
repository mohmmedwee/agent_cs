/** Events the server streams over SSE. Mirrors models/events.py. */
export type AgentEvent =
  | { type: 'text_delta'; text: string }
  | { type: 'reasoning_delta'; text: string }
  | { type: 'tool_call'; id: string; name: string; arguments: string }
  | { type: 'tool_result'; id: string; name: string; result: string }
  | { type: 'error'; message: string }
  | { type: 'done'; steps: number }

/**
 * One rendered piece of an assistant turn.
 *
 * The transcript is stored as blocks rather than as a single string so a
 * reloaded session shows what the loop actually did — which tools ran, how
 * long it thought — instead of just the final prose.
 */
export type Block =
  | { kind: 'text'; text: string }
  | { kind: 'reasoning'; text: string; seconds: number; open?: boolean }
  | { kind: 'skill'; name: string; loading?: boolean }
  | {
      kind: 'tool'
      id: string
      name: string
      args: string
      result?: string
      failed?: boolean
    }
  | { kind: 'error'; message: string }

export type Turn =
  | { role: 'user'; text: string }
  | { role: 'assistant'; blocks: Block[] }

export interface Session {
  id: string
  title: string
  createdAt: number
  updatedAt: number
  turns: Turn[]
}

export interface StoredFile {
  id: string
  name: string
  size: number
  content_type: string | null
  uploaded_at: string
  is_text: boolean
}

export interface Health {
  ok: boolean
  model: string | null
  upstream: string
  error: string | null
}
