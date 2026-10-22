import clsx from 'clsx'
import { ChevronDown, CircleCheck, Eye, EyeOff, LoaderCircle, Maximize2, Minimize2, Minus, MousePointerClick, Plus, RotateCcw, TriangleAlert } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import type { CellStatus, ExcelPreview, ParseOptions, TableInfo } from '../lib/types'
import { STATUS_META } from './excel'
import { SheetGrid } from './SheetGrid'

type Props = {
  preview: ExcelPreview | null
  loading: boolean
  error: string | null
  draft: ParseOptions
  onDraft: (next: ParseOptions) => void
  onSheet: (name: string) => void
}

export function SheetTabs({ preview, onSheet }: { preview: ExcelPreview; onSheet: (s: string) => void }) {
  return (
    <div className="scrollbar-thin flex gap-1 overflow-x-auto pb-1">
      {preview.sheets.map((s) => (
        <button
          key={s.name}
          onClick={() => onSheet(s.name)}
          className={clsx(
            'shrink-0 rounded-lg px-3 py-1.5 text-[12.5px] font-medium whitespace-nowrap transition',
            s.name === preview.sheet.name ? 'bg-white font-semibold text-tt-navy shadow-card ring-1 ring-tt-line' : 'text-tt-slate hover:bg-white/70 hover:text-tt-navy',
          )}
        >
          {s.name}
        </button>
      ))}
    </div>
  )
}

export function SheetPreview({ preview, loading, error, draft, onDraft, onSheet }: Props) {
  const [activeTable, setActiveTable] = useState<string | null>(null)
  const [selected, setSelected] = useState<string | null>(null)
  const [expanded, setExpanded] = useState(false)

  useEffect(() => {
    if (!expanded) return
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && setExpanded(false)
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [expanded])

  const counts = useMemo(() => {
    const c: Partial<Record<CellStatus, number>> = {}
    for (const r of preview?.sheet.rows ?? []) for (const cell of r.cells) c[cell.s] = (c[cell.s] ?? 0) + 1
    return c
  }, [preview])

  if (error) return <div className="rounded-2xl border border-tt-ember/30 bg-[#fdf0ea] p-5 text-[13.5px] text-[#8a3510]">{error}</div>
  if (!preview)
    return (
      <div className="flex h-64 items-center justify-center">
        <LoaderCircle className="animate-spin text-tt-electric" />
      </div>
    )

  const sheet = preview.sheet
  const selCell = selected
    ? sheet.rows.flatMap((r) => r.cells.map((c) => ({ ...c, r: r.r }))).find((c) => `${colLetterOf(c.c)}${c.r}` === selected)
    : null
  const sheetSkipDraft = !!draft.sheets?.[sheet.name]?.skip

  const setSheetSkip = (skip: boolean) => {
    const sheets = { ...(draft.sheets ?? {}) }
    if (skip) sheets[sheet.name] = { skip: true }
    else delete sheets[sheet.name]
    onDraft({ ...draft, sheets })
  }
  const setTable = (id: string, patch: { header_rows?: number | null; skip?: boolean }) => {
    const tables = { ...(draft.tables ?? {}) }
    const next = { ...(tables[id] ?? {}), ...patch }
    if (next.header_rows === null || next.header_rows === undefined) delete next.header_rows
    if (!next.skip) delete next.skip
    if (Object.keys(next).length) tables[id] = next
    else delete tables[id]
    onDraft({ ...draft, tables })
  }

  return (
    <>
      {expanded && <div className="fixed inset-0 z-40 bg-tt-midnight/55" onClick={() => setExpanded(false)} />}
    <div
      className={clsx(
        'flex min-h-0 flex-col gap-3',
        expanded ? 'fixed inset-2 z-50 rounded-3xl bg-tt-mist p-4 shadow-2xl sm:inset-4 sm:p-5' : 'h-full',
      )}
    >
      {expanded && (
        <div className="flex items-center gap-3">
          <div className="min-w-0 flex-1">
            <div className="truncate font-display text-[16px] font-bold text-tt-navy">{preview.file_name}</div>
            <div className="text-[12px] text-tt-slate">Sheet preview · press Esc to close</div>
          </div>
        </div>
      )}
      <div className="flex items-center gap-2">
        <div className="min-w-0 flex-1">
          <SheetTabs preview={preview} onSheet={(s) => { setSelected(null); setActiveTable(null); onSheet(s) }} />
        </div>
        <button
          onClick={() => setExpanded((e) => !e)}
          className={clsx(
            'inline-flex h-8 shrink-0 items-center gap-1.5 rounded-lg px-2.5 text-[12.5px] font-semibold transition',
            expanded ? 'bg-tt-navy text-white hover:bg-tt-midnight' : 'bg-white text-tt-slate ring-1 ring-tt-line hover:text-tt-navy hover:ring-tt-periwinkle',
          )}
          title={expanded ? 'Exit full screen (Esc)' : 'Full screen'}
          aria-label={expanded ? 'Exit full screen' : 'Full screen'}
        >
          {expanded ? <Minimize2 size={14} /> : <Maximize2 size={14} />}
          {expanded && 'Close'}
        </button>
      </div>

      <div className="flex flex-wrap items-center gap-x-4 gap-y-1">
        {(Object.keys(STATUS_META) as CellStatus[])
          .filter((s) => counts[s])
          .map((s) => (
            <span key={s} className="inline-flex cursor-help items-center gap-1.5 text-[11.5px] text-tt-slate" title={STATUS_META[s].explain}>
              <span className={clsx('h-2.5 w-2.5 rounded-[3px]', STATUS_META[s].dot)} />
              {STATUS_META[s].label}
              <span className="text-tt-slate/60">{counts[s]}</span>
            </span>
          ))}
        {loading && <LoaderCircle size={15} className="ml-1 animate-spin text-tt-electric" />}
        {sheet.truncated && (
          <span className="ml-auto text-[11.5px] text-tt-slate">
            Showing {sheet.shown_rows} of {sheet.max_row} rows · {sheet.shown_cols} of {sheet.max_col} columns
          </span>
        )}
      </div>

      <div className={clsx('grid min-h-0 flex-1 gap-3', expanded ? 'lg:grid-cols-[1fr_340px]' : 'xl:grid-cols-[1fr_340px]')}>
        <div className="flex min-h-[420px] min-w-0 flex-col gap-3">
          <div className="min-h-0 flex-1">
            <SheetGrid sheet={sheet} activeTable={activeTable} selected={selected} onSelect={setSelected} />
          </div>
          <div className="rounded-xl border border-tt-line bg-white px-4 py-2.5">
            {selCell ? (
              <div className="flex items-start gap-3">
                <span className="rounded-lg bg-tt-navy px-2 py-1 font-display text-[12px] font-bold text-white">{selected}</span>
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <span className={clsx('h-3 w-3 rounded-[4px]', STATUS_META[selCell.s].dot)} />
                    <span className="text-[13px] font-semibold text-tt-navy">{STATUS_META[selCell.s].label}</span>
                    <span className="text-[12px] text-tt-slate">{STATUS_META[selCell.s].explain}</span>
                  </div>
                  <p className="mt-1.5 max-h-24 overflow-y-auto text-[13px] whitespace-pre-line text-tt-ink [overflow-wrap:anywhere]">
                    {selCell.v}
                    {selCell.full && <span className="text-tt-slate"> (shortened in preview)</span>}
                  </p>
                </div>
              </div>
            ) : (
              <p className="flex items-center gap-2 text-[12.5px] text-tt-slate">
                <MousePointerClick size={15} className="text-tt-periwinkle" /> Click a cell to see how it was read.
              </p>
            )}
          </div>
        </div>

        <aside className="scrollbar-thin min-h-0 space-y-3 overflow-y-auto pr-1">
          <SheetCard sheet={sheet} onSelect={setSelected} included={!sheetSkipDraft} onIncluded={(on) => setSheetSkip(!on)} />
          {sheet.tables.map((t, i) => (
            <TableCard
              key={t.id}
              t={t}
              index={i + 1}
              draft={draft.tables?.[t.id]}
              active={activeTable === t.id}
              onHover={(on) => setActiveTable(on ? t.id : null)}
              onChange={(patch) => setTable(t.id, patch)}
            />
          ))}
        </aside>
      </div>
    </div>
    </>
  )
}

function colLetterOf(n: number) {
  let s = ''
  while (n > 0) {
    const m = (n - 1) % 26
    s = String.fromCharCode(65 + m) + s
    n = Math.floor((n - 1) / 26)
  }
  return s
}

function Toggle({ on, onChange }: { on: boolean; onChange: (v: boolean) => void }) {
  return (
    <button
      type="button"
      onClick={(e) => {
        e.preventDefault()
        onChange(!on)
      }}
      className={clsx('relative h-5 w-9 shrink-0 rounded-full transition', on ? 'bg-tt-electric' : 'bg-tt-line')}
      aria-pressed={on}
    >
      <span className={clsx('absolute top-0.5 h-4 w-4 rounded-full bg-white shadow transition-all', on ? 'left-[18px]' : 'left-0.5')} />
    </button>
  )
}

type SheetCardProps = { sheet: ExcelPreview['sheet']; onSelect: (a: string) => void; included: boolean; onIncluded: (on: boolean) => void }

function SheetCard({ sheet, onSelect, included, onIncluded }: SheetCardProps) {
  const c = sheet.coverage
  const ok = c.percent >= 99.9
  return (
    <div className="rounded-xl border border-tt-line bg-white">
      <div className="flex items-start gap-2.5 p-4">
        {ok ? <CircleCheck size={18} className="mt-px shrink-0 text-[#0b8f81]" /> : <TriangleAlert size={18} className="mt-px shrink-0 text-tt-amber" />}
        <div className="min-w-0">
          <div className="text-[13.5px] font-semibold text-tt-navy">{ok ? 'All data captured' : `${c.percent}% of the data captured`}</div>
          <div className="mt-0.5 text-[12px] leading-snug text-tt-slate">
            {sheet.record_count} record{sheet.record_count === 1 ? '' : 's'} stored
            {c.ignored_count > 0 && ` · ${c.ignored_count} picture or error cell${c.ignored_count === 1 ? '' : 's'} skipped`}
          </div>
        </div>
      </div>
      {c.missed.length > 0 && (
        <div className="mx-4 mb-4 rounded-lg bg-[#fdf0ea] p-2.5">
          <div className="text-[12px] font-semibold text-[#8a3510]">Not captured: click a cell to inspect it</div>
          <div className="mt-1.5 flex flex-wrap gap-1">
            {c.missed.slice(0, 12).map((m) => (
              <button key={m.cell} onClick={() => onSelect(m.cell)} className="rounded-md bg-white px-1.5 py-0.5 font-display text-[11px] font-bold text-[#8a3510] ring-1 ring-tt-ember/30" title={m.value}>
                {m.cell}
              </button>
            ))}
          </div>
        </div>
      )}
      <label className="flex cursor-pointer items-center justify-between gap-3 border-t border-tt-line px-4 py-3 select-none">
        <span>
          <span className="block text-[13px] font-medium text-tt-ink">Include in knowledge base</span>
          {!included && <span className="block text-[11.5px] text-[#a8471a]">Nothing from this sheet will be stored</span>}
        </span>
        <Toggle on={included} onChange={onIncluded} />
      </label>
    </div>
  )
}

type TableCardProps = {
  t: TableInfo
  index: number
  draft?: { header_rows?: number | null; skip?: boolean }
  active: boolean
  onHover: (on: boolean) => void
  onChange: (patch: { header_rows?: number | null; skip?: boolean }) => void
}

function TableCard({ t, index, draft, active, onHover, onChange }: TableCardProps) {
  const [open, setOpen] = useState(false)
  const applied = t.header_rows.length
  const value = draft?.header_rows ?? applied
  const pending = draft?.header_rows !== undefined && draft.header_rows !== applied
  const skip = draft?.skip ?? false
  const isText = t.kind === 'text' && !t.skipped
  return (
    <div
      onMouseEnter={() => onHover(true)}
      onMouseLeave={() => onHover(false)}
      className={clsx(
        'rounded-xl border bg-white p-4 transition',
        active ? 'border-tt-electric/60 ring-2 ring-tt-electric/10' : 'border-tt-line',
        skip && 'opacity-70',
      )}
    >
      <div className="flex items-center gap-2">
        <span className="text-[13.5px] font-semibold text-tt-navy">{isText ? 'Text block' : `Table ${index}`}</span>
        <span className="text-[11.5px] text-tt-slate/70">{t.range}</span>
        {t.overridden && <span className="rounded bg-tt-amber-tint px-1.5 py-0.5 text-[10.5px] font-semibold text-[#9a5a06]">Corrected</span>}
        {skip && <span className="rounded bg-[#fdf0ea] px-1.5 py-0.5 text-[10.5px] font-semibold text-[#8a3510]">Excluded</span>}
      </div>
      {t.title && <div className="mt-0.5 truncate text-[12.5px] text-tt-slate">{t.title}</div>}

      {isText ? (
        <p className="mt-1.5 text-[12px] text-tt-slate">Title or notes, stored as text ({t.preamble_rows.length} line{t.preamble_rows.length === 1 ? '' : 's'}).</p>
      ) : (
        <>
          <p className="mt-1.5 text-[12px] text-tt-slate">
            {t.records} record{t.records === 1 ? '' : 's'} · {t.columns.length} column{t.columns.length === 1 ? '' : 's'}
            {t.section_rows.length > 0 && ` · ${t.section_rows.length} section${t.section_rows.length === 1 ? '' : 's'}`}
          </p>

          <div className="mt-3 flex items-center justify-between gap-2 border-t border-tt-line pt-3">
            <div>
              <div className="text-[12.5px] font-medium text-tt-ink">Header rows</div>
              <div className="text-[11px] text-tt-slate">
                {pending ? <span className="font-semibold text-[#9a5a06]">changed from {applied}</span> : `detected ${t.header_rows_detected}`}
              </div>
            </div>
            <div className="flex items-center gap-1">
              <button onClick={() => onChange({ header_rows: Math.max(0, value - 1) })} className="flex h-7 w-7 items-center justify-center rounded-lg ring-1 ring-tt-line hover:bg-tt-mist" aria-label="Fewer header rows">
                <Minus size={13} />
              </button>
              <span className="w-7 text-center font-display text-[15px] font-bold text-tt-navy">{value}</span>
              <button onClick={() => onChange({ header_rows: Math.min(4, value + 1) })} className="flex h-7 w-7 items-center justify-center rounded-lg ring-1 ring-tt-line hover:bg-tt-mist" aria-label="More header rows">
                <Plus size={13} />
              </button>
              {(t.overridden || draft?.header_rows !== undefined) && (
                <button onClick={() => onChange({ header_rows: null })} className="ml-1 rounded-lg p-1.5 text-tt-slate hover:bg-tt-mist" title="Back to auto-detect">
                  <RotateCcw size={13} />
                </button>
              )}
            </div>
          </div>

          <button onClick={() => setOpen((o) => !o)} className="mt-3 flex w-full items-center justify-between text-[12px] font-medium text-tt-slate hover:text-tt-navy">
            {open ? 'Hide columns' : 'Show columns'}
            <ChevronDown size={14} className={clsx('transition', open && 'rotate-180')} />
          </button>
          {open && (
            <div className="mt-2 max-h-56 space-y-1 overflow-y-auto">
              {t.columns.map((c) => (
                <div key={c.col} className="flex items-start gap-2 text-[12px]">
                  <span className="w-6 shrink-0 font-display font-bold text-tt-slate">{c.col}</span>
                  <span className={clsx('min-w-0 flex-1 [overflow-wrap:anywhere]', c.name.startsWith('Column ') ? 'text-tt-ember italic' : 'text-tt-ink')}>
                    {c.name}
                  </span>
                  <span className="shrink-0 text-tt-slate/70">{c.filled}</span>
                </div>
              ))}
            </div>
          )}
        </>
      )}

      <div className="mt-2 flex justify-end">
        <button
          onClick={() => onChange({ skip: !skip })}
          className={clsx(
            'inline-flex items-center gap-1.5 rounded-md px-2 py-1 text-[12px] font-medium transition',
            skip ? 'text-tt-electric hover:bg-tt-electric/[0.06]' : 'text-tt-slate hover:bg-[#fdf0ea] hover:text-[#8a3510]',
          )}
        >
          {skip ? <Eye size={13} /> : <EyeOff size={13} />} {skip ? 'Include table' : 'Exclude table'}
        </button>
      </div>
    </div>
  )
}
