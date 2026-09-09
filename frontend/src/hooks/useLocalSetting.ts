import { useCallback, useState } from 'react'

/**
 * State that survives a reload, for preferences the server does not need to
 * know about: sidebar width, theme, effort level.
 */
export function useLocalSetting<T>(key: string, fallback: T) {
  const storageKey = `agent-console:${key}`

  const [value, setValue] = useState<T>(() => {
    try {
      const raw = localStorage.getItem(storageKey)
      return raw === null ? fallback : (JSON.parse(raw) as T)
    } catch {
      return fallback
    }
  })

  const update = useCallback(
    (next: T) => {
      setValue(next)
      try {
        localStorage.setItem(storageKey, JSON.stringify(next))
      } catch {
        // Private browsing can refuse writes; the setting just won't persist.
      }
    },
    [storageKey],
  )

  return [value, update] as const
}
