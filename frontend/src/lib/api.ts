import type {
  ConversationDetail,
  ConversationSummary,
  Effort,
  Health,
  ModelInfo,
  Skill,
  StoredFile,
  User,
  UserMemory,
} from '@/types'

/**
 * Thin wrapper over fetch.
 *
 * Auth rides on an HTTP-only cookie, so there is no token to attach — every
 * call just needs `credentials: 'include'`. A 401 is surfaced as a typed error
 * so the router can send the user to the login screen instead of each caller
 * inventing its own handling.
 */

export class ApiError extends Error {
  readonly status: number

  constructor(status: number, message: string) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }

  get isUnauthorized() {
    return this.status === 401
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(path, {
    credentials: 'include',
    ...init,
    headers:
      init.body instanceof FormData
        ? init.headers
        : { 'Content-Type': 'application/json', ...init.headers },
  })

  if (!response.ok) {
    throw new ApiError(response.status, await readError(response))
  }
  if (response.status === 204) {
    return undefined as T
  }
  return response.json() as Promise<T>
}

async function readError(response: Response): Promise<string> {
  try {
    const body = await response.json()
    const detail = body?.detail
    if (typeof detail === 'string') return detail
    // FastAPI validation errors arrive as a list of field problems.
    if (Array.isArray(detail) && detail.length) {
      return detail.map((item) => item.msg ?? String(item)).join(', ')
    }
  } catch {
    /* fall through to the status text */
  }
  return response.statusText || `Request failed (${response.status})`
}

const json = (body: unknown) => JSON.stringify(body)

export const api = {
  auth: {
    me: () => request<User>('/api/auth/me'),
    login: (email: string, password: string) =>
      request<User>('/api/auth/login', { method: 'POST', body: json({ email, password }) }),
    register: (email: string, display_name: string, password: string) =>
      request<User>('/api/auth/register', {
        method: 'POST',
        body: json({ email, display_name, password }),
      }),
    logout: () => request<void>('/api/auth/logout', { method: 'POST' }),
  },

  conversations: {
    list: () =>
      request<{ conversations: ConversationSummary[] }>('/api/conversations').then(
        (r) => r.conversations,
      ),
    create: (title = 'New chat') =>
      request<ConversationSummary>('/api/conversations', {
        method: 'POST',
        body: json({ title }),
      }),
    get: (id: string) => request<ConversationDetail>(`/api/conversations/${id}`),
    rename: (id: string, title: string) =>
      request<ConversationSummary>(`/api/conversations/${id}`, {
        method: 'PATCH',
        body: json({ title }),
      }),
    rewind: (id: string, keep: number) =>
      request<ConversationDetail>(`/api/conversations/${id}/rewind`, {
        method: 'POST',
        body: json({ keep }),
      }),
    remove: (id: string) =>
      request<void>(`/api/conversations/${id}`, { method: 'DELETE' }),
  },

  files: {
    list: () =>
      request<{ files: StoredFile[] }>('/api/files').then((r) => r.files),
    upload: (files: File[]) => {
      const form = new FormData()
      files.forEach((file) => form.append('files', file))
      return request<{ files: StoredFile[] }>('/api/files', {
        method: 'POST',
        body: form,
      }).then((r) => r.files)
    },
    remove: (id: string) => request<void>(`/api/files/${id}`, { method: 'DELETE' }),
    downloadUrl: (id: string) => `/api/files/${id}/download`,
    preview: (id: string) =>
      request<{ id: string; name: string; text: string; truncated: boolean }>(
        `/api/files/${id}/preview`,
      ),
  },

  memory: {
    list: () =>
      request<{ memories: UserMemory[] }>('/api/memory').then((r) => r.memories),
    create: (content: string) =>
      request<UserMemory>('/api/memory', {
        method: 'POST',
        body: json({ content }),
      }),
    update: (id: string, content: string) =>
      request<UserMemory>(`/api/memory/${id}`, {
        method: 'PATCH',
        body: json({ content }),
      }),
    remove: (id: string) =>
      request<void>(`/api/memory/${id}`, { method: 'DELETE' }),
  },

  skills: {
    list: () => request<{ skills: Skill[] }>('/api/skills').then((r) => r.skills),
  },

  models: () =>
    request<{ models: ModelInfo[]; current: string | null }>('/api/models'),

    chat: {
      approve: (body: { conversation_id: string; call_id: string; allowed: boolean }) =>
        request<void>('/api/chat/approve', { method: 'POST', body: json(body) }),
      stop: (conversation_id: string) =>
        request<void>('/api/chat/stop', {
          method: 'POST',
          body: json({ conversation_id }),
        }),
    },

  health: () => request<Health>('/api/health'),
  admin: {
    users: () =>
      request<{ users: User[] }>('/api/admin/users').then((r) => r.users),
  },
}

export type ChatPayload = {
  conversation_id: string
  message: string
  model?: string
  effort?: Effort
}
