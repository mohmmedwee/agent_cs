import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'

import { SpinnerIcon } from '@/components/Icons'
import { api } from '@/lib/api'

/**
 * Renders a real .pptx deck as stacked slides in the artifact pane.
 * Uses @aiden0z/pptx-renderer (list mode), lazy-loaded like docx/exceljs.
 */
export function PptxNativePreview({ fileId }: { fileId: string }) {
  const { t } = useTranslation()
  const hostRef = useRef<HTMLDivElement>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    let cancelled = false
    let viewer: { destroy: () => void } | null = null
    const abort = new AbortController()
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
        host.replaceChildren()

        const [{ PptxViewer, RECOMMENDED_ZIP_LIMITS }, buffer] = await Promise.all([
          import('@aiden0z/pptx-renderer'),
          api.files.downloadBytes(fileId),
        ])
        if (cancelled) return

        viewer = await PptxViewer.open(buffer, host, {
          renderMode: 'list',
          zipLimits: RECOMMENDED_ZIP_LIMITS,
          listOptions: { windowed: true },
          lazySlides: true,
          lazyMedia: true,
          signal: abort.signal,
        })
        if (cancelled) {
          viewer.destroy()
          viewer = null
          return
        }
        setLoading(false)
      } catch (problem) {
        if (cancelled || abort.signal.aborted) return
        setError(problem instanceof Error ? problem.message : String(problem))
        setLoading(false)
      }
    })()

    return () => {
      cancelled = true
      abort.abort()
      viewer?.destroy()
      viewer = null
      const host = hostRef.current
      if (host) host.replaceChildren()
    }
  }, [fileId])

  return (
    <div className="relative flex min-h-full w-full min-w-0 flex-col">
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
        className={`pptx-native-host w-full min-w-0 ${loading || error ? 'hidden' : ''}`}
      />
    </div>
  )
}
