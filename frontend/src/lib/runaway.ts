/** Collapse degenerate model spam (e.g. endless ههههه) in the live UI. */

const CHAR_RUN = 64
const UNIT_REPEATS = 24

export function isRunawayRepetition(text: string): boolean {
  if (text.length < CHAR_RUN) return false

  let run = 1
  for (let i = 1; i < text.length; i++) {
    if (text[i] === text[i - 1]) {
      run++
      if (run >= CHAR_RUN) return true
    } else {
      run = 1
    }
  }

  const tail = text.slice(-240)
  for (let size = 1; size <= 8; size++) {
    const unit = tail.slice(-size)
    if (!unit || !unit.trim()) continue
    let repeats = 0
    let cursor = tail.length
    while (cursor >= size && tail.slice(cursor - size, cursor) === unit) {
      repeats++
      cursor -= size
    }
    if (repeats >= UNIT_REPEATS) return true
  }
  return false
}

export function trimRunawayTail(text: string, keepRepeats = 8): string {
  if (!text) return text

  const last = text[text.length - 1]!
  let run = 0
  let index = text.length
  while (index > 0 && text[index - 1] === last) {
    run++
    index--
  }
  if (run >= CHAR_RUN) {
    return text.slice(0, index) + last.repeat(Math.min(keepRepeats, run))
  }

  const tail = text.slice(-240)
  for (let size = 1; size <= 8; size++) {
    const unit = tail.slice(-size)
    if (!unit || !unit.trim()) continue
    let repeats = 0
    let cursor = tail.length
    while (cursor >= size && tail.slice(cursor - size, cursor) === unit) {
      repeats++
      cursor -= size
    }
    if (repeats >= UNIT_REPEATS) {
      const head = text.slice(0, text.length - tail.length + cursor)
      return head + unit.repeat(Math.min(keepRepeats, repeats))
    }
  }
  return text
}
