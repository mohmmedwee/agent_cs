import type { AgentEvent } from '@/types'
import { ApiError, type ChatPayload } from '@/lib/api'

/**
 * POST /api/chat and yield each agent event as it arrives.
 *
 * EventSource can't be used here because the request is a POST with a body,
 * so the SSE framing is parsed by hand off the fetch stream.
 */
export async function* streamChat(
  payload: ChatPayload,
  signal: AbortSignal,
): AsyncGenerator<AgentEvent> {
  const response = await fetch('/api/chat', {
    method: 'POST',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
    signal,
  })
  if (!response.ok) {
    throw new ApiError(response.status, `server returned ${response.status}`)
  }
  if (!response.body) throw new Error('server sent no body')

  const reader = response.body.pipeThrough(new TextDecoderStream()).getReader()
  let carry = ''

  try {
    while (true) {
      const { value, done } = await reader.read()
      if (done) break
      carry += value

      // Frames are separated by a blank line; a partial tail is kept for the
      // next chunk. Handles \r\n as well, which some proxies introduce.
      const frames = carry.split(/\r?\n\r?\n/)
      carry = frames.pop() ?? ''

      for (const frame of frames) {
        const line = frame.split(/\r?\n/).find((l) => l.startsWith('data:'))
        if (!line) continue
        try {
          yield JSON.parse(line.slice(5).trim()) as AgentEvent
        } catch {
          // A malformed frame is not worth killing the stream over.
        }
      }
    }
  } finally {
    // Abort mid-stream leaves the reader open otherwise, holding the
    // connection until GC.
    await reader.cancel().catch(() => {})
  }
}
