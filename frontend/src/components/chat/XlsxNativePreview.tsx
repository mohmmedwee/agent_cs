import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'

import { SpinnerIcon } from '@/components/Icons'
import { api } from '@/lib/api'

type SheetView = {
  name: string
  rows: string[][]
}

const MAX_ROWS = 200
const MAX_COLS = 40

function cellText(value: unknown): string {
  if (value == null) return ''
  if (typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean') {
    return String(value)
  }
  if (value instanceof Date) return value.toLocaleString()
  if (typeof value === 'object' && value !== null && 'text' in value) {
    return String((value as { text: unknown }).text ?? '')
  }
  if (typeof value === 'object' && value !== null && 'result' in value) {
    return cellText((value as { result: unknown }).result)
  }
  return String(value)
}

/**
 * Renders a real .xlsx workbook as HTML tables (sheet tabs when needed).
 */
export function XlsxNativePreview({ fileId }: { fileId: string }) {
  const { t } = useTranslation()
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [sheets, setSheets] = useState<SheetView[]>([])
  const [active, setActive] = useState(0)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError('')
    setSheets([])
    setActive(0)

    void (async () => {
      try {
        const [{ default: ExcelJS }, buffer] = await Promise.all([
          import('exceljs'),
          api.files.downloadBytes(fileId),
        ])
        if (cancelled) return

        const workbook = new ExcelJS.Workbook()
        await workbook.xlsx.load(buffer)

        const parsed: SheetView[] = []
        workbook.eachSheet((worksheet) => {
          const rows: string[][] = []
          worksheet.eachRow({ includeEmpty: false }, (row, rowNumber) => {
            if (rowNumber > MAX_ROWS) return
            const cells: string[] = []
            const count = Math.min(row.cellCount, MAX_COLS)
            for (let col = 1; col <= count; col += 1) {
              cells.push(cellText(row.getCell(col).value))
            }
            // Drop fully empty trailing rows already skipped by includeEmpty.
            if (cells.some((cell) => cell.trim())) rows.push(cells)
          })
          parsed.push({ name: worksheet.name || `Sheet${parsed.length + 1}`, rows })
        })

        if (!cancelled) {
          setSheets(parsed)
          setLoading(false)
        }
      } catch (problem) {
        if (!cancelled) {
          setError(problem instanceof Error ? problem.message : String(problem))
          setLoading(false)
        }
      }
    })()

    return () => {
      cancelled = true
    }
  }, [fileId])

  if (loading) {
    return (
      <div className="flex items-center gap-2 p-4 text-sm text-ink-2">
        <SpinnerIcon width={16} height={16} />
        {t('common.loading')}
      </div>
    )
  }

  if (error) {
    return (
      <p className="p-4 text-sm text-error" role="alert">
        {error}
      </p>
    )
  }

  if (sheets.length === 0) {
    return <p className="p-4 text-sm text-ink-2">{t('chat.xlsxEmpty')}</p>
  }

  const sheet = sheets[Math.min(active, sheets.length - 1)]
  const width = Math.max(1, ...sheet.rows.map((row) => row.length))

  return (
    <div className="flex min-h-full min-w-0 flex-col gap-3">
      {sheets.length > 1 ? (
        <div className="flex flex-wrap gap-1.5">
          {sheets.map((item, index) => (
            <button
              key={`${item.name}-${index}`}
              type="button"
              onClick={() => setActive(index)}
              className={`rounded-lg px-3 py-1.5 text-xs font-medium transition
                ${
                  index === active
                    ? 'bg-primary-50 text-primary ring-1 ring-primary-200'
                    : 'bg-surface text-ink-2 ring-1 ring-line hover:text-ink'
                }`}
            >
              {item.name}
            </button>
          ))}
        </div>
      ) : null}

      <div
        className="min-w-0 overflow-auto rounded-xl bg-surface shadow-md
          ring-1 ring-line"
      >
        <table className="xlsx-preview-table w-max min-w-full border-collapse text-sm">
          <tbody>
            {sheet.rows.map((row, rowIndex) => (
              <tr key={rowIndex} className={rowIndex === 0 ? 'xlsx-preview-head' : undefined}>
                {Array.from({ length: width }, (_, colIndex) => {
                  const Tag = rowIndex === 0 ? 'th' : 'td'
                  return (
                    <Tag key={colIndex} dir="auto">
                      {row[colIndex] ?? ''}
                    </Tag>
                  )
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
