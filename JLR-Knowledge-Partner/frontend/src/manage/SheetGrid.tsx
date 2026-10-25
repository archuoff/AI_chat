import clsx from 'clsx'
import { Fragment, memo, useMemo } from 'react'
import { AuthImage } from '../lib/AuthImage'
import type { ExcelPicture, ExcelPreview } from '../lib/types'
import { colLetter, rangeBounds, STATUS_META } from './excel'

type Sheet = ExcelPreview['sheet']
type Props = {
  sheet: Sheet
  activeTable: string | null
  selected: string | null
  onSelect: (address: string | null) => void
  /** pictures are drawn in the cell they belong to (instead of the "[picture]" text) */
  pictures?: ExcelPicture[]
  showPictures?: boolean
  activePicture?: string | null
  onPicture?: (id: string | null) => void
}

const key = (r: number, c: number) => `${r}:${c}`

/** The original worksheet, merged cells included, coloured by what the parser did with each cell. */
export const SheetGrid = memo(function SheetGrid({ sheet, activeTable, selected, onSelect, pictures = [], showPictures = false, activePicture = null, onPicture }: Props) {
  const model = useMemo(() => {
    const cells = new Map<string, Sheet['rows'][number]['cells'][number]>()
    const usedRows = new Set<number>()
    for (const row of sheet.rows) {
      for (const cell of row.cells) cells.set(key(row.r, cell.c), cell)
      usedRows.add(row.r)
    }
    const spans = new Map<string, { rs: number; cs: number }>()
    const covered = new Set<string>()
    for (const m of sheet.merges) {
      spans.set(key(m.r0, m.c0), { rs: m.r1 - m.r0 + 1, cs: m.c1 - m.c0 + 1 })
      for (let r = m.r0; r <= m.r1; r++) {
        usedRows.add(r)
        for (let c = m.c0; c <= m.c1; c++) if (r !== m.r0 || c !== m.c0) covered.add(key(r, c))
      }
    }
    const picAt = new Map<string, ExcelPicture[]>()
    for (const p of pictures) {
      const k = key(p.r, p.c)
      picAt.set(k, [...(picAt.get(k) ?? []), p])
      for (let r = p.r; r <= p.r1; r++) usedRows.add(r) // a picture on an otherwise empty row keeps its row
    }
    // collapse long runs of empty rows (and never split a merged block)
    const lines: ({ kind: 'row'; r: number } | { kind: 'gap'; from: number; to: number })[] = []
    let r = 1
    while (r <= sheet.shown_rows) {
      if (usedRows.has(r)) {
        lines.push({ kind: 'row', r })
        r++
        continue
      }
      let end = r
      while (end + 1 <= sheet.shown_rows && !usedRows.has(end + 1)) end++
      if (end - r + 1 >= 3) lines.push({ kind: 'gap', from: r, to: end })
      else for (let x = r; x <= end; x++) lines.push({ kind: 'row', r: x })
      r = end + 1
    }
    const tables = sheet.tables.map((t) => ({ id: t.id, ...rangeBounds(t.range) }))
    return { cells, spans, covered, lines, tables, picAt }
  }, [sheet, pictures])

  const active = activeTable ? model.tables.find((t) => t.id === activeTable) : null
  const inActive = (r: number, c: number) => !active || (r >= active.r0 && r <= active.r1 && c >= active.c0 && c <= active.c1)
  const cols = Array.from({ length: sheet.shown_cols }, (_, i) => i + 1)

  return (
    <div className="scrollbar-thin h-full overflow-auto rounded-2xl border border-tt-line bg-white">
      <table className="border-separate border-spacing-0 text-[12px] leading-snug">
        <thead>
          <tr>
            <th className="sticky top-0 left-0 z-30 h-8 w-11 border-r border-b border-tt-line bg-tt-mist" />
            {cols.map((c) => (
              <th
                key={c}
                className="sticky top-0 z-20 h-8 min-w-[110px] border-r border-b border-tt-line bg-tt-mist px-2 font-display text-[11px] font-semibold text-tt-slate"
              >
                {colLetter(c)}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {model.lines.map((line) =>
            line.kind === 'gap' ? (
              <tr key={`g${line.from}`}>
                <th className="sticky left-0 z-10 border-r border-b border-tt-line bg-tt-mist px-1 font-display text-[10px] font-semibold text-tt-slate/60">
                  ⋮
                </th>
                <td colSpan={cols.length} className="border-b border-tt-line bg-tt-mist/40 px-3 py-1 text-[11px] text-tt-slate/60 italic">
                  rows {line.from}–{line.to} empty
                </td>
              </tr>
            ) : (
              <tr key={line.r}>
                <th className="sticky left-0 z-10 border-r border-b border-tt-line bg-tt-mist px-1 font-display text-[11px] font-semibold text-tt-slate">
                  {line.r}
                </th>
                {cols.map((c) => {
                  const k = key(line.r, c)
                  if (model.covered.has(k)) return <Fragment key={k} />
                  const cell = model.cells.get(k)
                  const span = model.spans.get(k)
                  const address = `${colLetter(c)}${line.r}`
                  const meta = cell ? STATUS_META[cell.s] : null
                  const here = showPictures ? model.picAt.get(k) : undefined
                  return (
                    <td
                      key={k}
                      rowSpan={span?.rs}
                      colSpan={span?.cs}
                      onClick={() => onSelect(cell ? (selected === address ? null : address) : null)}
                      title={cell ? `${address} · ${meta?.label}` : address}
                      className={clsx(
                        'max-w-[260px] min-w-[110px] border-r border-b border-tt-line px-2 py-1.5 align-top',
                        meta ? meta.cls : 'bg-white',
                        cell && 'cursor-pointer',
                        !inActive(line.r, c) && 'opacity-30',
                        selected === address && 'outline-2 -outline-offset-2 outline-tt-electric',
                      )}
                    >
                      {here && (
                        <div className="flex flex-wrap gap-1">
                          {here.map((p) => (
                            <button
                              key={p.id}
                              type="button"
                              onClick={(e) => {
                                e.stopPropagation()
                                onPicture?.(activePicture === p.id ? null : p.id)
                              }}
                              title={`Picture in ${address}: click for details`}
                              className={clsx(
                                'overflow-hidden rounded-md bg-white ring-1 transition hover:ring-tt-electric',
                                activePicture === p.id ? 'ring-2 ring-tt-electric' : 'ring-tt-line',
                              )}
                            >
                              <AuthImage id={p.id} alt={`Picture in ${address}`} className="block h-16 max-w-[140px] min-w-10 object-contain" />
                            </button>
                          ))}
                        </div>
                      )}
                      {cell && !(here && cell.v.startsWith('[picture')) && (
                        <div className="line-clamp-3 whitespace-pre-line [overflow-wrap:anywhere]">{cell.v}</div>
                      )}
                    </td>
                  )
                })}
              </tr>
            ),
          )}
        </tbody>
      </table>
    </div>
  )
})
