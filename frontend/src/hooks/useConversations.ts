import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { api } from '@/lib/api'
import type { ConversationSummary } from '@/types'

/**
 * The list and detail keys are deliberately siblings rather than parent and
 * child. Were the list `['conversations']`, invalidating it after a turn would
 * prefix-match the open conversation too and refetch it — replacing the live
 * transcript with the stored one, which drops the reasoning block because
 * reasoning is never persisted.
 */
export const conversationKeys = {
  all: ['conversations', 'list'] as const,
  detail: (id: string) => ['conversations', 'detail', id] as const,
}

export function useConversations() {
  return useQuery({
    queryKey: conversationKeys.all,
    queryFn: api.conversations.list,
  })
}

export function useConversation(id: string | undefined) {
  return useQuery({
    queryKey: conversationKeys.detail(id ?? ''),
    queryFn: () => api.conversations.get(id!),
    enabled: Boolean(id),
    // The transcript is rebuilt locally while streaming; refetching on focus
    // mid-stream would replace live blocks with a stale snapshot.
    refetchOnWindowFocus: false,
  })
}

export function useCreateConversation() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (title?: string) => api.conversations.create(title),
    onSuccess: (created) => {
      queryClient.setQueryData<ConversationSummary[]>(conversationKeys.all, (old) =>
        old ? [created, ...old] : [created],
      )
    },
  })
}

export function useRenameConversation() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ id, title }: { id: string; title: string }) =>
      api.conversations.rename(id, title),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: conversationKeys.all })
    },
  })
}

export function useDeleteConversation() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => api.conversations.remove(id),
    onSuccess: (_result, id) => {
      queryClient.setQueryData<ConversationSummary[]>(conversationKeys.all, (old) =>
        old?.filter((conversation) => conversation.id !== id),
      )
      queryClient.removeQueries({ queryKey: conversationKeys.detail(id) })
    },
  })
}
