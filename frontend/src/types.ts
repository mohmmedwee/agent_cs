/** Events the server streams over SSE. Mirrors models/events.py. */
import type { ApprovalCard } from '@/components/chat/ApprovalDiffCard'

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
  | {
      type: 'tool_approval'
      id: string
      name: string
      arguments: string
      approval_card?: ApprovalCard | null
    }
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
      /** Human-in-the-loop: waiting for Allow / Deny. */
      awaitingApproval?: boolean
      /** Approval POST in flight. */
      approvalPending?: boolean
      /** Server-built edit_docx diff card (render only). */
      approvalCard?: ApprovalCard | null
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
  parent_id?: string | null
  branched_at_position?: number | null
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
  /** Older turns were summarized for the model; UI still shows the full chat. */
  context_compressed?: boolean
  /** Rolling summary the model sees instead of older turns. */
  context_summary?: string | null
  /** How many leading transcript messages are covered by the summary. */
  summarized_count?: number
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

export interface UserMemory {
  id: string
  content: string
  source: string
  created_at: string
  updated_at: string
}

export interface Skill {
  name: string
  description: string
  source: 'builtin' | 'user' | string
  id?: string | null
  enabled?: boolean
}

export interface UserSkill {
  id: string
  name: string
  description: string
  body: string
  enabled: boolean
  created_at: string
  updated_at: string
  source?: string
}

export interface ModelInfo {
  id: string
  loaded: boolean
}

export type Effort = 'minimal' | 'low' | 'medium' | 'xhigh'

/** Map legacy stored values (`high`) onto Qwen3.8's real levels. */
export function normalizeEffort(value: string | null | undefined): Effort {
  if (value === 'high' || value === 'x-high') return 'xhigh'
  if (value === 'minimal' || value === 'low' || value === 'medium' || value === 'xhigh') {
    return value
  }
  return 'medium'
}

export interface Health {
  ok: boolean
  model: string | null
  upstream: string
  error: string | null
  context_window?: number | null
  revision?: string | null
}
