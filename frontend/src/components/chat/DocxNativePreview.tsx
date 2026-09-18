import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'

import { SpinnerIcon } from '@/components/Icons'
import { api } from '@/lib/api'

const HOST_CSS = `
  :host {
    display: block;
    width: 100%;
  }
  .docx-native-wrapper {
    background: transparent !important;
    padding: 0 !important;
    align-items: stretch !important;
  }
  .docx-native-wrapper > section.docx-native {
    margin-inline: auto !important;
    margin-bottom: 1.5rem !important;
    max-width: 100% !important;
    box-shadow: 0 1px 3px rgb(0 0 0 / 0.12) !important;
    overflow-x: auto;
  }
  .docx-native-wrapper img {
    max-width: 100%;
    height: auto;
  }
`

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

        const shadow =
          host.shadowRoot ?? host.attachShadow({ mode: 'open' })
        shadow.innerHTML = ''

        const localStyle = document.createElement('style')
        localStyle.textContent = HOST_CSS

        // Styles go here (isolated). Body/content goes in bodyMount.
        const styleMount = document.createElement('div')
        const bodyMount = document.createElement('div')
        shadow.append(localStyle, styleMount, bodyMount)

        await renderAsync(buffer, bodyMount, styleMount, {
          className: 'docx-native',
          inWrapper: true,
          ignoreWidth: true,
          breakPages: true,
          renderHeaders: true,
          renderFooters: true,
          // Base64-encoding every embedded image balloons memory on large
          // Solution Design docs; keep blob/object URLs instead.
          useBase64URL: false,
        })
        if (!cancelled) setLoading(false)
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
        <div className="flex items-center gap-2 p-4 text-sm text-secondary">
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
        className={`docx-native-host w-full min-w-0 ${loading || error ? 'hidden' : ''}`}
      />
    </div>
  )
}
