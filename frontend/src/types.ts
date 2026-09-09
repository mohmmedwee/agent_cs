/** Events the server streams over SSE. Mirrors models/events.py. */
export type AgentEvent =
  | { type: 'text_delta'; text: string }
  | { type: 'reasoning_delta'; text: string }
  | {
      type: 'tool_call_delta'
      index: number
      id: string
      name: string
      arguments_chars: number
    }
  | { type: 'tool_call'; id: string; name: string; arguments: string }
  | { type: 'tool_result'; id: string; name: string; result: string }
  | { type: 'error'; message: string }
  | { type: 'done'; steps: number }

/**
 * One rendered piece of an assistant turn.
 *
 * The transcript is stored as blocks rather than as a single string so a
 * reloaded conversation shows what the loop actually did — which tools ran,
 * how long it thought — instead of just the final prose.
 */
export type Block =
  | { kind: 'text'; text: string }
  | { kind: 'reasoning'; text: string; seconds: number; open?: boolean }
  | { kind: 'skill'; name: string; args?: string; loading?: boolean }
  | {
      kind: 'tool'
      id: string
      name: string
      args: string
      result?: string
      failed?: boolean
      /** True while the model is still generating this call's arguments. */
      streaming?: boolean
      argumentsChars?: number
    }
  | { kind: 'error'; message: string }

export type Turn =
  | { role: 'user'; text: string }
  | { role: 'assistant'; blocks: Block[] }

export interface User {
  id: string
  email: string
  display_name: string
  is_admin: boolean
  created_at: string
}

export interface ConversationSummary {
  id: string
  title: string
  created_at: string
  updated_at: string
}

export interface StoredMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
  blocks: Block[] | null
  created_at: string
}

export interface ConversationDetail extends ConversationSummary {
  messages: StoredMessage[]
}

export interface StoredFile {
  id: string
  name: string
  size: number
  content_type: string | null
  uploaded_at: string
  is_text: boolean
  is_image: boolean
}

export interface Skill {
  name: string
  description: string
  source?: string
}

export interface ModelInfo {
  id: string
  loaded: boolean
}

export type Effort = 'minimal' | 'low' | 'medium' | 'high'

export interface Health {
  ok: boolean
  model: string | null
  upstream: string
  error: string | null
}
