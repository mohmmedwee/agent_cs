/** Ask once; safe to call on every send. */
export async function ensureNotifyPermission(): Promise<boolean> {
  if (typeof window === 'undefined' || !('Notification' in window)) return false
  if (Notification.permission === 'granted') return true
  if (Notification.permission === 'denied') return false
  try {
    return (await Notification.requestPermission()) === 'granted'
  } catch {
    return false
  }
}

/**
 * Desktop notification when a chat finishes in the background.
 * Skips if the user is already looking at that conversation with the tab focused.
 */
export function notifyChatDone(options: {
  conversationId: string
  title: string
  body: string
}): void {
  if (typeof window === 'undefined' || !('Notification' in window)) return
  if (Notification.permission !== 'granted') return

  const onThisChat = window.location.pathname.includes(options.conversationId)
  if (onThisChat && !document.hidden) return

  try {
    const note = new Notification(options.title, {
      body: options.body,
      tag: `chat-done-${options.conversationId}`,
    })
    note.onclick = () => {
      window.focus()
      window.location.assign(`/chat/${options.conversationId}`)
      note.close()
    }
  } catch {
    // Some embedded browsers reject Notification construction.
  }
}
