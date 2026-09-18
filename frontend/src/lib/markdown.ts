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

function splitCells(line: string): string[] {
  return line
    .replace(/^\s*\|/, '')
    .replace(/\|\s*$/, '')
    .split('|')
    .map((cell) => cell.trim())
}

function isSeparatorRow(line: string): boolean {
  const cells = splitCells(line)
  return cells.length > 0 && cells.every((cell) => /^:?-{3,}:?$/.test(cell))
}

/** GFM pipe tables — what the model emits for "make a table". */
function renderTable(lines: string[]): string {
  const header = splitCells(lines[0])
  const align = splitCells(lines[1]).map((cell) => {
    if (cell.startsWith(':') && cell.endsWith(':')) return 'center'
    if (cell.endsWith(':')) return 'right'
    if (cell.startsWith(':')) return 'left'
    return ''
  })
  const body = lines.slice(2).map(splitCells)

  const th = header
    .map((cell, index) => {
      const style = align[index] ? ` style="text-align:${align[index]}"` : ''
      return `<th dir="auto"${style}>${cell}</th>`
    })
    .join('')

  const rows = body
    .map((cells) => {
      const tds = header
        .map((_, index) => {
          const style = align[index] ? ` style="text-align:${align[index]}"` : ''
          return `<td dir="auto"${style}>${cells[index] ?? ''}</td>`
        })
        .join('')
      return `<tr>${tds}</tr>`
    })
    .join('')

  return `<div class="table-wrap"><table><thead><tr>${th}</tr></thead><tbody>${rows}</tbody></table></div>`
}

/**
 * If the block is a table (optionally preceded by a prose line), return HTML
 * for the prose + table. Otherwise null.
 */
function tryRenderTableBlock(block: string): string | null {
  const lines = block.split('\n')
  let start = -1
  for (let i = 0; i < lines.length - 1; i++) {
    if (lines[i].includes('|') && isSeparatorRow(lines[i + 1])) {
      start = i
      break
    }
  }
  if (start < 0) return null

  let end = start + 2
  while (end < lines.length && lines[end].includes('|')) end += 1

  const tableLines = lines.slice(start, end)
  if (tableLines.length < 2) return null

  const before = lines.slice(0, start).join('\n').trim()
  const after = lines.slice(end).join('\n').trim()
  const table = renderTable(tableLines)

  const parts: string[] = []
  if (before) parts.push(`<p dir="auto">${before.replace(/\n/g, '<br>')}</p>`)
  parts.push(table)
  if (after) parts.push(`<p dir="auto">${after.replace(/\n/g, '<br>')}</p>`)
  return parts.join('')
}

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
    // Images: same-origin API paths only (docx media + file downloads).
    .replace(
      /!\[([^\]]*)\]\((\/api\/files\/[^)\s]+)\)/g,
      (_match, alt: string, href: string) =>
        `<img src="${href}" alt="${alt}" class="preview-embed" loading="lazy" />`,
    )
    // Absolute http(s) or a same-origin path — the download links the agent
    // hands back are relative, and anything else (javascript:, data:) is left
    // as plain text on purpose. The href is already escaped, so it cannot
    // break out of the attribute.
    .replace(
      /\[([^\]]+)\]\((https?:\/\/[^)\s]+|\/[^)\s]*)\)/g,
      (_match, label: string, href: string) =>
        href.startsWith('/')
          ? `<a href="${href}">${label}</a>`
          : `<a href="${href}" target="_blank" rel="noopener">${label}</a>`,
    )

  const out: string[] = []
  for (const para of s.split(/\n{2,}/)) {
    const t = para.trim()
    if (!t) continue

    if (/^\u0000\d+\u0000$/.test(t)) {
      out.push(t)
      continue
    }

    const asTable = tryRenderTableBlock(t)
    if (asTable) {
      out.push(asTable)
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
