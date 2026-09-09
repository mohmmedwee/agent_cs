import { useCallback, useEffect, useMemo, useState } from 'react'
import type { Session, Turn } from '../types'
import {
  emptySession,
  loadActiveId,
  loadSessions,
  saveActiveId,
  saveSessions,
  titleFor,
} from '../lib/storage'

/** Owns the session list and keeps it mirrored into localStorage. */
export function useSessions() {
  const [sessions, setSessions] = useState<Session[]>(() => {
    const stored = loadSessions()
    return stored.length ? stored : [emptySession()]
  })

  const [activeId, setActiveId] = useState<string>(() => {
    const stored = loadActiveId()
    const all = loadSessions()
    if (stored && all.some((s) => s.id === stored)) return stored
    return all[0]?.id ?? ''
  })

  // A first run has no stored id; adopt whichever session we started with.
  useEffect(() => {
    if (!activeId && sessions[0]) setActiveId(sessions[0].id)
  }, [activeId, sessions])

  useEffect(() => saveSessions(sessions), [sessions])
  useEffect(() => {
    if (activeId) saveActiveId(activeId)
  }, [activeId])

  const active = useMemo(
    () => sessions.find((s) => s.id === activeId) ?? sessions[0],
    [sessions, activeId],
  )

  const setTurns = useCallback(
    (update: Turn[] | ((previous: Turn[]) => Turn[])) => {
      setSessions((all) =>
        all.map((session) => {
          if (session.id !== activeId) return session
          const turns =
            typeof update === 'function' ? update(session.turns) : update
          return {
            ...session,
            turns,
            title: titleFor(turns),
            updatedAt: Date.now(),
          }
        }),
      )
    },
    [activeId],
  )

  const newChat = useCallback(() => {
    setSessions((all) => {
      // Reuse an untouched blank rather than stacking up empty sessions.
      const blank = all.find((s) => s.turns.length === 0)
      if (blank) {
        setActiveId(blank.id)
        return all
      }
      const created = emptySession()
      setActiveId(created.id)
      return [created, ...all]
    })
  }, [])

  const removeSession = useCallback((id: string) => {
    setSessions((all) => {
      const rest = all.filter((s) => s.id !== id)
      const next = rest.length ? rest : [emptySession()]
      setActiveId((current) =>
        current === id ? next[0].id : current,
      )
      return next
    })
  }, [])

  const ordered = useMemo(
    () => sessions.slice().sort((a, b) => b.updatedAt - a.updatedAt),
    [sessions],
  )

  return {
    sessions: ordered,
    active,
    activeId,
    selectSession: setActiveId,
    setTurns,
    newChat,
    removeSession,
  }
}
