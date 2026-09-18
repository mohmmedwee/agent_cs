import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'

import { SpinnerIcon } from '@/components/Icons'
import { api } from '@/lib/api'

type CellView = {
  text: string
  bold: boolean
}

type SheetView = {
  name: string
  rows: CellView[][]
  /** Excel row numbers for each displayed body row (1-based). */
  rowNumbers: number[]
  truncatedRows: boolean
  truncatedCols: boolean
  maxCol: number
}

const MAX_ROWS = 200
const MAX_COLS = 40

function columnLetter(index: number): string {
  let n = index + 1
  let label = ''
  while (n > 0) {
    const rem = (n - 1) % 26
    label = String.fromCharCode(65 + rem) + label
    n = Math.floor((n - 1) / 26)
  }
  return label
}

/** Strip leftover Markdown emphasis from older workbooks. */
function displayCell(raw: string, boldFromFont: boolean): CellView {
  let text = raw
  let bold = boldFromFont
  const wrapped = text.match(/^\*\*([\s\S]*)\*\*$/)
  if (wrapped) {
    text = wrapped[1]
    bold = true
  }
  const underscored = text.match(/^__([\s\S]*)__$/)
  if (underscored) {
    text = underscored[1]
    bold = true
  }
  return { text, bold }
}

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

function cellBold(font: { bold?: boolean } | undefined): boolean {
  return Boolean(font?.bold)
}

/**
 * Renders a real .xlsx workbook as an Excel-like grid (A/B/C, row numbers,
 * sheet tabs along the bottom).
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
          const dim = worksheet.dimensions
          const lastRow = Math.min(dim?.bottom ?? 0, MAX_ROWS)
          const lastCol = Math.min(Math.max(dim?.right ?? 1, 1), MAX_COLS)
          const truncatedRows = (dim?.bottom ?? 0) > MAX_ROWS
          const truncatedCols = (dim?.right ?? 0) > MAX_COLS

          const rows: CellView[][] = []
          const rowNumbers: number[] = []

          if (lastRow === 0) {
            parsed.push({
              name: worksheet.name || `Sheet${parsed.length + 1}`,
              rows,
              rowNumbers,
              truncatedRows,
              truncatedCols,
              maxCol: lastCol,
            })
            return
          }

          for (let rowNumber = 1; rowNumber <= lastRow; rowNumber += 1) {
            const row = worksheet.getRow(rowNumber)
            const cells: CellView[] = []
            for (let col = 1; col <= lastCol; col += 1) {
              const cell = row.getCell(col)
              cells.push(displayCell(cellText(cell.value), cellBold(cell.font)))
            }
            rows.push(cells)
            rowNumbers.push(rowNumber)
          }

          parsed.push({
            name: worksheet.name || `Sheet${parsed.length + 1}`,
            rows,
            rowNumbers,
            truncatedRows,
            truncatedCols,
            maxCol: lastCol,
          })
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
  const width = Math.max(sheet.maxCol, 1, ...sheet.rows.map((row) => row.length))
  const truncated = sheet.truncatedRows || sheet.truncatedCols

  return (
    <div className="xlsx-preview flex min-h-0 min-w-0 flex-1 flex-col">
      {truncated ? (
        <p className="shrink-0 px-1 pb-2 text-[11px] text-ink-3">
          {t('chat.xlsxTruncated', { rows: MAX_ROWS, cols: MAX_COLS })}
        </p>
      ) : null}

      <div className="xlsx-preview-frame min-h-0 min-w-0 flex-1 overflow-auto">
        <table className="xlsx-preview-table">
          <thead>
            <tr>
              <th className="xlsx-preview-corner" scope="col">
                <span className="sr-only"> </span>
              </th>
              {Array.from({ length: width }, (_, colIndex) => (
                <th key={colIndex} className="xlsx-preview-colhead" scope="col">
                  {columnLetter(colIndex)}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {sheet.rows.length === 0 ? (
              <tr>
                <th className="xlsx-preview-rowhead" scope="row">
                  1
                </th>
                {Array.from({ length: width }, (_, colIndex) => (
                  <td key={colIndex} />
                ))}
              </tr>
            ) : (
              sheet.rows.map((row, rowIndex) => {
                const excelRow = sheet.rowNumbers[rowIndex] ?? rowIndex + 1
                const headerish =
                  excelRow === 1 && row.some((cell) => cell.bold)
                return (
                  <tr
                    key={excelRow}
                    className={headerish ? 'xlsx-preview-head' : undefined}
                  >
                    <th className="xlsx-preview-rowhead" scope="row">
                      {excelRow}
                    </th>
                    {Array.from({ length: width }, (_, colIndex) => {
                      const cell = row[colIndex]
                      const Tag = headerish ? 'th' : 'td'
                      return (
                        <Tag
                          key={colIndex}
                          dir="auto"
                          className={cell?.bold ? 'xlsx-preview-bold' : undefined}
                        >
                          {cell?.text ?? ''}
                        </Tag>
                      )
                    })}
                  </tr>
                )
              })
            )}
          </tbody>
        </table>
      </div>

      <div
        className="xlsx-preview-tabs shrink-0"
        role="tablist"
        aria-label={t('chat.xlsxSheets')}
      >
        {sheets.map((item, index) => (
          <button
            key={`${item.name}-${index}`}
            type="button"
            role="tab"
            aria-selected={index === active}
            onClick={() => setActive(index)}
            className={`xlsx-preview-tab ${index === active ? 'is-active' : ''}`}
            title={item.name}
          >
            {item.name}
          </button>
        ))}
      </div>
    </div>
  )
}
