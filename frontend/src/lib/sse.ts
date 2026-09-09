import type { AgentEvent } from '../types'

export interface ChatMessage {
  role: 'user' | 'assistant'
  content: string
}

/**
 * POST /api/chat and yield each agent event as it arrives.
 *
 * EventSource can't be used here because the request is a POST with a body,
 * so the SSE framing is parsed by hand off the fetch stream.
 */
export async function* streamChat(
  messages: ChatMessage[],
  signal: AbortSignal,
): AsyncGenerator<AgentEvent> {
  const response = await fetch('/api/chat', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ messages }),
    signal,
  })
  if (!response.ok) throw new Error(`server returned ${response.status}`)
  if (!response.body) throw new Error('server sent no body')

  const reader = response.body.pipeThrough(new TextDecoderStream()).getReader()
  let carry = ''

  while (true) {
    const { value, done } = await reader.read()
    if (done) break
    carry += value

    const frames = carry.split('\n\n')
    carry = frames.pop() ?? ''

    for (const frame of frames) {
      if (!frame.startsWith('data: ')) continue
      try {
        yield JSON.parse(frame.slice(6)) as AgentEvent
      } catch {
        // A malformed frame is not worth killing the stream over.
      }
    }
  }
}
