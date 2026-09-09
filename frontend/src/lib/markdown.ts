/**
 * A deliberately small markdown renderer.
 *
 * No library: the built bundle should stay self-contained and this covers what
 * the model actually emits. `dir="auto"` goes on each block rather than the
 * container, so Arabic prose flows RTL without dragging code and lists with it.
 */

const escapeHtml = (s: string) =>
  s.replace(
    /[&<>"]/g,
    (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[c] as string,
  )

export { escapeHtml }

export function renderMarkdown(src: string): string {
  const blocks: string[] = []

  let s = src.replace(
    /```(\w*)\n?([\s\S]*?)```/g,
    (_m, _lang, code: string) =>
      `\u0000${
        blocks.push(
          `<pre><code>${escapeHtml(code.replace(/\n$/, ''))}</code></pre>`,
        ) - 1
      }\u0000`,
  )

  s = escapeHtml(s)
    .replace(/`([^`\n]+)`/g, '<code>$1</code>')
    .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
    .replace(/(^|\W)\*([^*\n]+)\*/g, '$1<em>$2</em>')
    .replace(
      /\[([^\]]+)\]\((https?:[^)\s]+)\)/g,
      '<a href="$2" target="_blank" rel="noopener">$1</a>',
    )

  const out: string[] = []
  for (const para of s.split(/\n{2,}/)) {
    const t = para.trim()
    if (!t) continue

    if (/^\u0000\d+\u0000$/.test(t)) {
      out.push(t)
      continue
    }

    const heading = t.match(/^(#{1,3})\s+(.*)$/m)
    if (heading && t.startsWith('#')) {
      const level = heading[1].length
      out.push(`<h${level} dir="auto">${heading[2]}</h${level}>`)
      continue
    }

    if (/^\s*[-*]\s+/.test(t)) {
      const items = t
        .split('\n')
        .map((l) => `<li>${l.replace(/^\s*[-*]\s+/, '')}</li>`)
        .join('')
      out.push(`<ul dir="auto">${items}</ul>`)
      continue
    }

    if (/^\s*\d+[.)]\s+/.test(t)) {
      const items = t
        .split('\n')
        .map((l) => `<li>${l.replace(/^\s*\d+[.)]\s+/, '')}</li>`)
        .join('')
      out.push(`<ol dir="auto">${items}</ol>`)
      continue
    }

    out.push(`<p dir="auto">${t.replace(/\n/g, '<br>')}</p>`)
  }

  return out
    .join('')
    .replace(/\u0000(\d+)\u0000/g, (_m, i: string) => blocks[Number(i)])
}
