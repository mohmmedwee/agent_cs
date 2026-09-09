import type { Block, Turn } from '@/types'

/** Rough overhead for system prompt + skill index on every request. */
export const CONTEXT_OVERHEAD_TOKENS = 2_500

/**
 * Approximate tokens from text. Latin ≈ 4 chars/token; Arabic/CJK denser.
 * Good enough for a usage meter — not a billing tokenizer.
 */
export function estimateTokens(text: string): number {
  if (!text) return 0
  let tokens = 0
  for (const char of text) {
    const code = char.codePointAt(0) ?? 0
    // Arabic, Hebrew, CJK ranges tend toward ~1–2 chars per token.
    if (
      (code >= 0x0600 && code <= 0x06ff) ||
      (code >= 0x0750 && code <= 0x077f) ||
      (code >= 0x4e00 && code <= 0x9fff) ||
      (code >= 0x3400 && code <= 0x4dbf)
    ) {
      tokens += 0.6
    } else {
      tokens += 0.25
    }
  }
  return Math.max(1, Math.ceil(tokens))
}

/**
 * Text that is replayed to the model on later turns.
 * Tool args/results and reasoning live in UI blocks only — counting them
 * inflated the meter past 70% while summarization (content-only) stayed quiet.
 */
function modelFacingBlockText(block: Block): string {
  switch (block.kind) {
    case 'text':
      return block.text
    case 'reasoning':
    case 'skill':
    case 'tool':
      return ''
    case 'error':
      return block.message
  }
}

export function estimateTurnTokens(turns: Turn[]): number {
  let total = 0
  for (const turn of turns) {
    if (turn.role === 'user') {
      total += estimateTokens(turn.text)
    } else {
      for (const block of turn.blocks) {
        const text = modelFacingBlockText(block)
        if (text) total += estimateTokens(text)
      }
    }
    total += 4 // role framing — matches backend estimate_message_tokens
  }
  return total
}

/** Tokens the next request is likely to send (summary + unsummarized turns). */
export function estimateModelContextTokens(options: {
  turns: Turn[]
  contextWindow: number
  contextSummary?: string | null
  summarizedCount?: number
}): { used: number; ratio: number; percent: number } {
  const summarizedCount = Math.max(
    0,
    Math.min(options.summarizedCount ?? 0, options.turns.length),
  )
  const summary = options.contextSummary?.trim() || ''
  let used = CONTEXT_OVERHEAD_TOKENS
  if (summary) {
    used += estimateTokens(
      `Earlier in this conversation (compressed for length):\n\n${summary}`,
    )
    used += estimateTokens("Understood — I'll use that summary as prior context.")
    used += 8
  }
  used += estimateTurnTokens(options.turns.slice(summarizedCount))
  const ratio = Math.min(1, used / Math.max(1, options.contextWindow))
  return { used, ratio, percent: Math.round(ratio * 100) }
}

export type SessionStatus = 'ready' | 'working' | 'approval' | 'queued'

export function sessionStatus(options: {
  busy: boolean
  awaitingApproval: boolean
  queueLength: number
}): SessionStatus {
  if (options.awaitingApproval) return 'approval'
  if (options.busy) return 'working'
  if (options.queueLength > 0) return 'queued'
  return 'ready'
}

export function formatTokenCount(n: number): string {
  if (n >= 1000) return `${(n / 1000).toFixed(n >= 10_000 ? 0 : 1)}k`
  return String(n)
}
