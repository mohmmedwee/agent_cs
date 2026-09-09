import { useMemo } from 'react'

import { renderMarkdown } from '@/lib/markdown'

/**
 * The renderer escapes all HTML before emitting its own tags, so model output
 * cannot inject markup — that is what makes this use of dangerouslySetInnerHTML
 * safe.
 */
export function Markdown({ text, compact = false }: { text: string; compact?: boolean }) {
  const html = useMemo(() => renderMarkdown(text), [text])
  return (
    <div
      className={compact ? 'prose-agent prose-agent--compact' : 'prose-agent'}
      dangerouslySetInnerHTML={{ __html: html }}
    />
  )
}
