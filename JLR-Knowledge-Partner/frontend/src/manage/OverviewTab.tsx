import clsx from 'clsx'
import { ChevronRight, CircleCheck, TriangleAlert, Wrench } from 'lucide-react'
import type { DocumentInfo } from '../lib/types'

const complete = (p: number) => p >= 99.9

export function OverviewTab({ doc, onOpenSheet }: { doc: DocumentInfo; onOpenSheet: (sheet: string) => void }) {
  const isExcel = doc.file_type === 'xlsx' || doc.file_type === 'xlsm'
  const sheets = Object.entries(doc.stats.sheets ?? {})
  const coverage = doc.stats.coverage_percent
  const toReview = sheets.filter(([, s]) => !s.skipped && !complete(s.coverage.percent)).length
  const corrections = [
    ...Object.entries(doc.parse_options?.sheets ?? {}).filter(([, v]) => v.skip).map(([s]) => `Sheet "${s}" excluded`),
    ...Object.entries(doc.parse_options?.tables ?? {}).flatMap(([id, v]) => [
      ...(v.header_rows !== undefined && v.header_rows !== null ? [`${id}: ${v.header_rows} header row${v.header_rows === 1 ? '' : 's'}`] : []),
      ...(v.skip ? [`${id}: excluded`] : []),
    ]),
  ]

  const ok = coverage === undefined || complete(coverage)
  const stats: [string, string | number][] = isExcel
    ? [
        ['Sheets', sheets.length],
        ['Records', doc.records],
        ['Search chunks', doc.chunks],
        ['Captured', coverage !== undefined ? `${coverage}%` : '–'],
      ]
    : [
        [doc.stats.pages ? 'Pages' : doc.stats.slides ? 'Slides' : 'Text blocks', doc.stats.pages ?? doc.stats.slides ?? doc.text_blocks],
        ['Text blocks', doc.text_blocks],
        ['Table records', doc.records],
        ['Search chunks', doc.chunks],
      ]

  return (
    <div className="scrollbar-thin h-full overflow-y-auto pr-1">
      <div className="mx-auto max-w-4xl space-y-4">
        {/* verdict + key numbers */}
        <section className="rounded-xl border border-tt-line bg-white">
          <div className="flex items-start gap-3 px-5 pt-4 pb-3.5">
            {ok ? <CircleCheck size={20} className="mt-0.5 shrink-0 text-[#0b8f81]" /> : <TriangleAlert size={20} className="mt-0.5 shrink-0 text-tt-amber" />}
            <div>
              <div className="font-display text-[14.5px] font-bold text-tt-navy">
                {ok ? (isExcel ? 'All data captured' : 'Processed and searchable') : `${toReview} sheet${toReview === 1 ? '' : 's'} need${toReview === 1 ? 's' : ''} a look`}
              </div>
              <p className="mt-0.5 text-[12.5px] text-tt-slate">
                {ok
                  ? 'Everything readable in this document is stored, and the assistant can answer from it.'
                  : 'Some values were not stored. Open the sheet preview to see which cells and adjust the table settings.'}
              </p>
            </div>
          </div>
          <dl className="grid grid-cols-2 border-t border-tt-line sm:grid-cols-4">
            {stats.map(([label, value], i) => (
              <div key={label} className={clsx('px-5 py-3', i > 0 && 'sm:border-l sm:border-tt-line')}>
                <dt className="text-[11.5px] text-tt-slate">{label}</dt>
                <dd className="mt-0.5 font-display text-[18px] font-bold text-tt-navy">{value}</dd>
              </div>
            ))}
          </dl>
        </section>

        {corrections.length > 0 && (
          <section className="flex gap-3 rounded-xl border border-tt-amber/40 bg-tt-amber-tint/60 px-5 py-3.5">
            <Wrench size={16} className="mt-0.5 shrink-0 text-[#9a5a06]" />
            <div className="text-[12.5px] text-[#7a4705]">
              <div className="font-semibold">Your corrections</div>
              <div className="mt-0.5">{corrections.join(' · ')}</div>
            </div>
          </section>
        )}

        {isExcel && sheets.length > 0 && (
          <section className="overflow-hidden rounded-xl border border-tt-line bg-white">
            <div className="flex items-center px-5 py-3">
              <span className="font-display text-[14px] font-bold text-tt-navy">Sheets</span>
              <span className="ml-auto text-[12px] text-tt-slate">Click a sheet to preview it</span>
            </div>
            <ul>
              {sheets.map(([name, s]) => {
                const p = s.coverage.percent
                return (
                  <li key={name}>
                    <button
                      onClick={() => onOpenSheet(name)}
                      className="group flex w-full items-center gap-4 border-t border-tt-line px-5 py-2.5 text-left transition hover:bg-tt-mist/50"
                    >
                      <span className="min-w-0 flex-1 truncate text-[13px] font-medium text-tt-ink">{name}</span>
                      <span className="w-24 text-right text-[12.5px] text-tt-slate">
                        {s.records} record{s.records === 1 ? '' : 's'}
                      </span>
                      <span className="w-28 text-right text-[12.5px]">
                        {s.skipped ? (
                          <span className="text-tt-slate/70">Excluded</span>
                        ) : complete(p) ? (
                          <span className="inline-flex items-center gap-1 text-[#0b8f81]">
                            <CircleCheck size={13} /> Complete
                          </span>
                        ) : (
                          <span className="inline-flex items-center gap-1.5 font-semibold text-[#b86a0b]">
                            <span className="h-1.5 w-1.5 rounded-full bg-tt-amber" /> {p}% captured
                          </span>
                        )}
                      </span>
                      <ChevronRight size={15} className="text-tt-slate/40 transition group-hover:translate-x-0.5 group-hover:text-tt-electric" />
                    </button>
                  </li>
                )
              })}
            </ul>
          </section>
        )}

        {doc.warnings?.length > 0 && (
          <section className="rounded-xl border border-tt-line bg-white px-5 py-3.5">
            <div className="text-[12.5px] font-semibold text-tt-navy">Processing notes</div>
            <ul className="mt-1 space-y-0.5 text-[12.5px] text-tt-slate">
              {doc.warnings.map((w) => (
                <li key={w}>{w}</li>
              ))}
            </ul>
          </section>
        )}

        <details className="group rounded-xl border border-tt-line bg-white px-5 py-3 text-[12.5px]">
          <summary className="flex cursor-pointer list-none items-center gap-1.5 font-semibold text-tt-slate select-none hover:text-tt-navy">
            <ChevronRight size={14} className="transition group-open:rotate-90" /> Details
          </summary>
          <dl className="mt-3 grid gap-x-8 gap-y-2 sm:grid-cols-2">
            {Object.entries(doc.meta ?? {}).map(([k, v]) => (
              <div key={k} className="flex gap-2">
                <dt className="text-tt-slate capitalize">{k.replace(/_/g, ' ')}</dt>
                <dd className="text-tt-ink">{Array.isArray(v) ? v.join(', ') : String(v)}</dd>
              </div>
            ))}
            <div className="flex gap-2">
              <dt className="text-tt-slate">Embedding model</dt>
              <dd className="text-tt-ink">{doc.embedding_model ?? '–'}</dd>
            </div>
            <div className="flex min-w-0 gap-2">
              <dt className="shrink-0 text-tt-slate">Content hash</dt>
              <dd className="truncate font-mono text-[11.5px] text-tt-ink" title={doc.content_hash}>
                {doc.content_hash.slice(0, 16)}…
              </dd>
            </div>
          </dl>
        </details>
      </div>
    </div>
  )
}
