import { LoaderCircle, Search } from 'lucide-react'
import { useMemo, useState } from 'react'
import type { ExcelPreview } from '../lib/types'
import { SheetTabs } from './SheetPreview'

export function RecordsTab({ preview, onSheet }: { preview: ExcelPreview | null; onSheet: (s: string) => void }) {
  const [q, setQ] = useState('')
  const term = q.trim().toLowerCase()
  const tables = useMemo(() => {
    if (!preview) return []
    return preview.sheet.tables
      .filter((t) => (preview.sheet.records[t.id] ?? []).length > 0)
      .map((t) => {
        const rows = preview.sheet.records[t.id]
        const names = t.columns.map((c) => c.name).filter((n) => rows.some((r) => n in r.fields))
        const hasSection = rows.some((r) => r.section.length > 0)
        const shown = term ? rows.filter((r) => JSON.stringify(r.fields).toLowerCase().includes(term)) : rows
        return { t, names, hasSection, rows: shown, total: rows.length }
      })
  }, [preview, term])

  if (!preview)
    return (
      <div className="flex h-64 items-center justify-center">
        <LoaderCircle className="animate-spin text-tt-electric" />
      </div>
    )

  return (
    <div className="flex h-full min-h-0 flex-col gap-3">
      <div className="flex flex-wrap items-center gap-3">
        <div className="min-w-0 flex-1">
          <SheetTabs preview={preview} onSheet={onSheet} />
        </div>
        <div className="relative w-full sm:w-64">
          <Search size={15} className="absolute top-1/2 left-3 -translate-y-1/2 text-tt-slate/60" />
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Filter records…"
            className="w-full rounded-xl border border-tt-line bg-white py-2 pr-3 pl-9 text-[13px] outline-none focus:border-tt-periwinkle"
          />
        </div>
      </div>
      <p className="text-[12.5px] text-tt-slate">Each row is stored as one record, exactly as the assistant reads and quotes it.</p>
      <div className="scrollbar-thin min-h-0 flex-1 space-y-4 overflow-y-auto">
        {tables.length === 0 && <p className="py-10 text-center text-[13px] text-tt-slate">No table records on this sheet.</p>}
        {tables.map(({ t, names, hasSection, rows, total }) => (
          <section key={t.id} className="rounded-2xl border border-tt-line bg-white">
            <div className="flex flex-wrap items-center gap-2 border-b border-tt-line px-4 py-3">
              <span className="text-[13.5px] font-semibold text-tt-navy">{t.title || preview.sheet.name}</span>
              <span className="text-[11.5px] text-tt-slate/70">{t.range}</span>
              <span className="ml-auto text-[12px] text-tt-slate">
                {term ? `${rows.length} of ${total}` : total} records
              </span>
            </div>
            <div className="scrollbar-thin max-h-[60vh] overflow-auto">
              <table className="w-max min-w-full border-separate border-spacing-0 text-left text-[12.5px]">
                <thead>
                  <tr>
                    <th className="sticky top-0 left-0 z-20 border-b border-tt-line bg-[#f4f5fb] px-3 py-2 text-[11.5px] font-semibold text-tt-slate">Row</th>
                    {hasSection && <th className="sticky top-0 z-10 border-b border-tt-line bg-[#f4f5fb] px-3 py-2 text-[11.5px] font-semibold text-tt-navy">Section</th>}
                    {names.map((n) => (
                      <th key={n} className="sticky top-0 z-10 max-w-[260px] min-w-[140px] border-b border-tt-line bg-[#f4f5fb] px-3 py-2 text-[11.5px] font-semibold text-tt-navy">
                        {n}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {rows.map((r) => (
                    <tr key={r.row} className="hover:bg-tt-mist/60">
                      <td className="sticky left-0 border-b border-tt-line bg-white px-3 py-2 align-top text-tt-slate/70">{r.row}</td>
                      {hasSection && <td className="border-b border-tt-line px-3 py-2 align-top text-[#0b6f64]">{r.section.slice(-1)[0] ?? ''}</td>}
                      {names.map((n) => (
                        <td key={n} className="max-w-[260px] border-b border-tt-line px-3 py-2 align-top" title={r.fields[n] != null ? String(r.fields[n]) : ''}>
                          <div className="line-clamp-4 whitespace-pre-line [overflow-wrap:anywhere]">{r.fields[n] != null ? String(r.fields[n]) : ''}</div>
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        ))}
      </div>
    </div>
  )
}
