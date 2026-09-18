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
  yield* readSseStream(await postSse('/api/chat', payload, signal), signal)
}

/** Reattach to a run that survived a refresh / navigate-away. */
export async function* watchChat(
  conversationId: string,
  signal: AbortSignal,
): AsyncGenerator<AgentEvent> {
  yield* readSseStream(
    await postSse('/api/chat/watch', { conversation_id: conversationId }, signal),
    signal,
  )
}

async function postSse(
  path: string,
  body: unknown,
  signal: AbortSignal,
): Promise<Response> {
  const response = await fetch(path, {
    method: 'POST',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
    signal,
  })
  if (!response.ok) {
    throw new ApiError(response.status, `server returned ${response.status}`)
  }
  if (!response.body) throw new Error('server sent no body')
  return response
}

async function* readSseStream(
  response: Response,
  signal: AbortSignal,
): AsyncGenerator<AgentEvent> {
  const reader = response.body!.pipeThrough(new TextDecoderStream()).getReader()
  let carry = ''

  try {
    while (true) {
      if (signal.aborted) break
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
