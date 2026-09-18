import type { ConversationSummary } from '@/types'

export type ConversationGroupKey = 'today' | 'yesterday' | 'week' | 'older'

export interface ConversationGroup {
  key: ConversationGroupKey
  items: ConversationSummary[]
}

function startOfLocalDay(date: Date): Date {
  return new Date(date.getFullYear(), date.getMonth(), date.getDate())
}

/**
 * Group conversations by updated_at (local calendar day).
 * Preserves input order within each group; drops empty groups.
 */
export function groupConversations(
  list: ConversationSummary[],
  now = new Date(),
): ConversationGroup[] {
  const todayStart = startOfLocalDay(now)
  const yesterdayStart = new Date(todayStart)
  yesterdayStart.setDate(yesterdayStart.getDate() - 1)
  const weekStart = new Date(todayStart)
  weekStart.setDate(weekStart.getDate() - 7)

  const buckets: Record<ConversationGroupKey, ConversationSummary[]> = {
    today: [],
    yesterday: [],
    week: [],
    older: [],
  }

  for (const item of list) {
    const updated = new Date(item.updated_at)
    if (Number.isNaN(updated.getTime())) {
      buckets.older.push(item)
      continue
    }
    if (updated >= todayStart) {
      buckets.today.push(item)
    } else if (updated >= yesterdayStart) {
      buckets.yesterday.push(item)
    } else if (updated >= weekStart) {
      buckets.week.push(item)
    } else {
      buckets.older.push(item)
    }
  }

  const order: ConversationGroupKey[] = ['today', 'yesterday', 'week', 'older']
  return order
    .filter((key) => buckets[key].length > 0)
    .map((key) => ({ key, items: buckets[key] }))
}
