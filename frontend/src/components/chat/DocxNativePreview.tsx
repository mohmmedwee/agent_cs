import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'

import { SpinnerIcon } from '@/components/Icons'
import { api } from '@/lib/api'

/**
 * Page-faithful Word preview. Keep real page width (ignoreWidth: false) so
 * tables and long paths are not crushed into the side panel.
 */
const HOST_CSS = `
  :host {
    display: block;
    width: 100%;
  }
  .docx-native-wrapper {
    background: transparent !important;
    padding: 0 0 2rem !important;
    align-items: flex-start !important;
    overflow: visible !important;
    height: auto !important;
    max-height: none !important;
  }
  .docx-native-wrapper > section.docx-native {
    box-sizing: border-box !important;
    margin: 0 auto 1.25rem !important;
    background: #fff !important;
    /* docx-preview defaults to overflow:hidden + fixed page height, which
       clips charts/tables that don't fit a single Word page box. */
    overflow: visible !important;
    height: auto !important;
    max-height: none !important;
    min-height: 0 !important;
    box-shadow:
      0 1px 2px rgb(28 26 36 / 0.06),
      0 8px 24px -16px rgb(28 26 36 / 0.22) !important;
  }
  .docx-native-wrapper article {
    overflow: visible !important;
    overflow-wrap: anywhere;
    word-break: break-word;
  }
  .docx-native-wrapper table {
    width: 100% !important;
    max-width: 100% !important;
    border-collapse: collapse !important;
    table-layout: auto !important;
  }
  .docx-native-wrapper td,
  .docx-native-wrapper th {
    overflow-wrap: anywhere !important;
    word-break: break-word !important;
    vertical-align: top !important;
    hyphens: auto;
  }
  .docx-native-wrapper img,
  .docx-native-wrapper svg {
    max-width: 100% !important;
    height: auto !important;
  }
  .docx-native-wrapper p.docx-toc-stub {
    color: #8a857c !important;
    font-size: 0.8125rem !important;
    font-style: italic !important;
  }
`

function polishRenderedDoc(root: ParentNode) {
  const paragraphs = root.querySelectorAll('p')
  for (const node of paragraphs) {
    const text = (node.textContent || '').trim()
    if (
      /update field/i.test(text) ||
      /right-click and choose/i.test(text) ||
      /انقر بزر الماوس الأيمن/i.test(text)
    ) {
      node.classList.add('docx-toc-stub')
      if (/update field/i.test(text) && text.length < 120) {
        node.textContent =
          'Table of contents opens fully in Word / Google Docs after download.'
      }
    }
  }
}

/**
 * Renders real .docx bytes inside a Shadow DOM so docx-preview styles and
 * @font-face rules cannot leak into (and corrupt) the Cleverso UI.
 */
export function DocxNativePreview({ fileId }: { fileId: string }) {
  const { t } = useTranslation()
  const hostRef = useRef<HTMLDivElement>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError('')

    void (async () => {
      try {
        const host = hostRef.current
        if (!host) {
          setError('Preview container missing')
          setLoading(false)
          return
        }

        const [{ renderAsync }, buffer] = await Promise.all([
          import('docx-preview'),
          api.files.downloadBytes(fileId),
        ])
        if (cancelled) return

        const shadow = host.shadowRoot ?? host.attachShadow({ mode: 'open' })
        shadow.innerHTML = ''

        const localStyle = document.createElement('style')
        localStyle.textContent = HOST_CSS

        const styleMount = document.createElement('div')
        const bodyMount = document.createElement('div')
        shadow.append(localStyle, styleMount, bodyMount)

        await renderAsync(buffer, bodyMount, styleMount, {
          className: 'docx-native',
          inWrapper: true,
          // Real page width for tables; grow height so nothing is clipped.
          ignoreWidth: false,
          ignoreHeight: true,
          breakPages: true,
          ignoreLastRenderedPageBreak: false,
          renderHeaders: true,
          renderFooters: true,
          useBase64URL: false,
        })
        if (cancelled) return
        polishRenderedDoc(bodyMount)
        // Belt-and-suspenders: clear any inline page-height clips.
        for (const section of bodyMount.querySelectorAll('section.docx-native')) {
          const el = section as HTMLElement
          el.style.height = 'auto'
          el.style.maxHeight = 'none'
          el.style.overflow = 'visible'
        }
        setLoading(false)
      } catch (problem) {
        if (!cancelled) {
          setError(problem instanceof Error ? problem.message : String(problem))
          setLoading(false)
        }
      }
    })()

    return () => {
      cancelled = true
      const host = hostRef.current
      if (host?.shadowRoot) host.shadowRoot.innerHTML = ''
    }
  }, [fileId])

  return (
    <div className="relative min-h-full w-full min-w-0">
      {loading && (
        <div className="flex items-center gap-2 p-4 text-sm text-ink-2">
          <SpinnerIcon width={16} height={16} />
          {t('common.loading')}
        </div>
      )}
      {error && (
        <p className="p-4 text-sm text-error" role="alert">
          {error}
        </p>
      )}
      <div
        ref={hostRef}
        className={`docx-native-host w-full min-w-0 overflow-x-auto ${
          loading || error ? 'hidden' : ''
        }`}
      />
    </div>
  )
}
