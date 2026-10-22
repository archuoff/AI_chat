import { ChevronRight, CircleCheck, Hourglass, Images, LoaderCircle, Lock, Plus, Sparkles, TriangleAlert } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { api } from '../lib/api'
import { domainVisual } from '../lib/domains'
import { cleanName, FileBadge, fileVisual, timeAgo } from '../lib/format'
import type { DocumentInfo, Domain, ImagesSummary } from '../lib/types'

type Props = {
  docs: DocumentInfo[]
  domains: Domain[]
  onOpen: (docId: string) => void
  onDomain: (domainId: string) => void
  onAdd: () => void
}

// one colour per file family for the type bar
const TYPE_COLOR: Record<string, string> = { Excel: '#12a596', PowerPoint: '#f2a039', Word: '#698cf7', PDF: '#d75d27', CSV: '#0b6f64' }

const fmt = (n: number) => n.toLocaleString('en-GB')
const isExcel = (d: DocumentInfo) => d.file_type === 'xlsx' || d.file_type === 'xlsm'
const needsReview = (d: DocumentInfo) => d.stats?.coverage_percent !== undefined && d.stats.coverage_percent < 99.9

export function LibraryDashboard({ docs, domains, onOpen, onDomain, onAdd }: Props) {
  const [pics, setPics] = useState<ImagesSummary | null>(null)
  useEffect(() => {
    api.imagesSummary().then(setPics).catch(() => {})
  }, [docs])
  const picRunning = pics?.job.state === 'running'
  useEffect(() => {
    if (!picRunning) return
    const t = setInterval(() => api.imagesSummary().then(setPics).catch(() => {}), 2000)
    return () => clearInterval(t)
  }, [picRunning])
  const s = useMemo(() => {
    const records = docs.reduce((a, d) => a + d.records, 0)
    const chunks = docs.reduce((a, d) => a + d.chunks, 0)
    const excel = docs.filter((d) => isExcel(d) && d.stats?.coverage_percent !== undefined)
    const coverage = excel.length ? excel.reduce((a, d) => a + (d.stats.coverage_percent ?? 0), 0) / excel.length : null
    const attention = docs.filter(needsReview)
    const confidential = docs.filter((d) => d.confidential).length
    const types = new Map<string, number>()
    for (const d of docs) types.set(fileVisual(d.file_type).label, (types.get(fileVisual(d.file_type).label) ?? 0) + 1)
    const recent = [...docs].sort((a, b) => +new Date(b.ingested_at) - +new Date(a.ingested_at)).slice(0, 5)
    const byDomain = domains
      .filter((d) => d.id !== 'unassigned' || docs.some((x) => (x.domain ?? 'unassigned') === 'unassigned'))
      .map((d) => {
        const ds = docs.filter((x) => (x.domain ?? 'unassigned') === d.id)
        return { ...d, files: ds.length, chunks: ds.reduce((a, x) => a + x.chunks, 0), records: ds.reduce((a, x) => a + x.records, 0) }
      })
    const maxChunks = Math.max(1, ...byDomain.map((d) => d.chunks))
    return { records, chunks, coverage, attention, confidential, types: [...types.entries()].sort((a, b) => b[1] - a[1]), recent, byDomain, maxChunks }
  }, [docs, domains])

  const kpis: { label: string; value: string; note?: string }[] = [
    { label: 'Documents', value: fmt(docs.length), note: s.confidential ? `${s.confidential} confidential` : 'none confidential' },
    { label: 'Records', value: fmt(s.records), note: 'rows from tables' },
    { label: 'Search chunks', value: fmt(s.chunks), note: 'what the assistant searches' },
    { label: 'Data captured', value: s.coverage === null ? '–' : `${Math.round(s.coverage * 10) / 10}%`, note: 'average across Excel files' },
  ]

  return (
    <div className="scrollbar-thin h-full overflow-y-auto">
      <div className="mx-auto max-w-5xl space-y-4 px-5 py-6 sm:px-8">
        <div className="flex flex-wrap items-end gap-3">
          <div className="min-w-0 flex-1">
            <h2 className="font-display text-[19px] font-bold text-tt-navy">Knowledge library</h2>
            <p className="mt-0.5 text-[13px] text-tt-slate">Everything the assistant can answer from, at a glance. Select a document on the left to inspect it.</p>
          </div>
          <button onClick={onAdd} className="inline-flex items-center gap-1.5 rounded-lg bg-tt-electric px-3.5 py-2 text-[13px] font-semibold text-white transition hover:bg-tt-electric-600">
            <Plus size={15} /> Add documents
          </button>
        </div>

        {/* key numbers */}
        <section className="grid grid-cols-2 overflow-hidden rounded-xl border border-tt-line bg-white lg:grid-cols-4">
          {kpis.map((k, i) => (
            <div key={k.label} className={['px-5 py-4', i % 2 ? 'border-l border-tt-line' : '', i >= 2 ? 'border-t border-tt-line lg:border-t-0' : '', i === 2 ? 'lg:border-l' : ''].join(' ')}>
              <div className="text-[12px] text-tt-slate">{k.label}</div>
              <div className="mt-1 font-display text-[24px] leading-none font-bold text-tt-navy">{k.value}</div>
              {k.note && <div className="mt-1.5 text-[11.5px] text-tt-slate/70">{k.note}</div>}
            </div>
          ))}
        </section>

        {/* attention */}
        {s.attention.length === 0 ? (
          <section className="flex items-center gap-3 rounded-xl border border-tt-line bg-white px-5 py-3.5">
            <CircleCheck size={18} className="shrink-0 text-[#0b8f81]" />
            <p className="text-[13px] text-tt-ink">
              <b className="font-semibold text-tt-navy">Nothing needs attention.</b> <span className="text-tt-slate">Every document was fully captured.</span>
            </p>
          </section>
        ) : (
          <section className="rounded-xl border border-tt-amber/40 bg-white">
            <div className="flex items-center gap-2.5 px-5 pt-3.5 pb-2">
              <TriangleAlert size={17} className="text-tt-amber" />
              <span className="text-[13.5px] font-semibold text-tt-navy">
                {s.attention.length} document{s.attention.length === 1 ? '' : 's'} need{s.attention.length === 1 ? 's' : ''} a look
              </span>
              <span className="text-[12.5px] text-tt-slate">some values were not stored</span>
            </div>
            <ul className="pb-1.5">
              {s.attention.map((d) => (
                <li key={d.doc_id}>
                  <button onClick={() => onOpen(d.doc_id)} className="group flex w-full items-center gap-3 px-5 py-2 text-left hover:bg-tt-mist/50">
                    <FileBadge type={d.file_type} size="sm" />
                    <span className="min-w-0 flex-1 truncate text-[13px] text-tt-ink">{cleanName(d.file_name)}</span>
                    <span className="text-[12.5px] font-semibold text-[#b86a0b]">{d.stats.coverage_percent}% captured</span>
                    <ChevronRight size={15} className="text-tt-slate/40 group-hover:text-tt-electric" />
                  </button>
                </li>
              ))}
            </ul>
          </section>
        )}

        {pics && pics.counts.total > 0 && <PicturesCard pics={pics} onStarted={setPics} />}

        <div className="grid gap-4 lg:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)]">
          {/* by domain */}
          <section className="min-w-0 rounded-xl border border-tt-line bg-white">
            <div className="flex items-center px-5 pt-4 pb-2">
              <span className="font-display text-[14px] font-bold text-tt-navy">By domain</span>
              <span className="ml-auto text-[12px] text-tt-slate">Click to filter the list</span>
            </div>
            <ul className="pb-2">
              {s.byDomain.map((d) => {
                const v = domainVisual(d.id)
                return (
                  <li key={d.id}>
                    <button
                      onClick={() => d.files && onDomain(d.id)}
                      disabled={!d.files}
                      title={d.description}
                      className="group flex w-full items-center gap-3 px-5 py-2.5 text-left transition enabled:hover:bg-tt-mist/50 disabled:cursor-default"
                    >
                      <span className="h-2 w-2 shrink-0 rounded-full" style={{ background: v.color }} />
                      <span className="w-32 shrink-0 truncate text-[13px] font-medium text-tt-ink">{d.name}</span>
                      <span className="block h-1.5 min-w-10 flex-1 overflow-hidden rounded-full bg-tt-mist">
                        <span className="block h-full rounded-full" style={{ width: `${(d.chunks / s.maxChunks) * 100}%`, background: v.color, opacity: 0.75 }} />
                      </span>
                      <span className="shrink-0 text-right text-[12.5px] whitespace-nowrap text-tt-slate">
                        {d.files ? (
                          <>
                            <b className="font-semibold text-tt-navy">{d.files}</b> file{d.files === 1 ? '' : 's'}
                          </>
                        ) : (
                          <span className="text-tt-slate/60">No documents yet</span>
                        )}
                      </span>
                    </button>
                  </li>
                )
              })}
            </ul>
          </section>

          <div className="min-w-0 space-y-4">
            {/* by type */}
            <section className="rounded-xl border border-tt-line bg-white px-5 py-4">
              <div className="font-display text-[14px] font-bold text-tt-navy">By file type</div>
              <div className="mt-3 flex h-2 overflow-hidden rounded-full bg-tt-mist">
                {s.types.map(([label, n]) => (
                  <span key={label} style={{ width: `${(n / Math.max(1, docs.length)) * 100}%`, background: TYPE_COLOR[label] ?? '#9aa0b4' }} title={`${label}: ${n}`} />
                ))}
              </div>
              <ul className="mt-3 grid grid-cols-2 gap-x-4 gap-y-1.5">
                {s.types.map(([label, n]) => (
                  <li key={label} className="flex items-center gap-2 text-[12.5px] text-tt-slate">
                    <span className="h-2 w-2 rounded-full" style={{ background: TYPE_COLOR[label] ?? '#9aa0b4' }} />
                    {label}
                    <b className="ml-auto font-semibold text-tt-navy">{n}</b>
                  </li>
                ))}
              </ul>
            </section>

            {/* recent */}
            <section className="rounded-xl border border-tt-line bg-white">
              <div className="px-5 pt-4 pb-1.5 font-display text-[14px] font-bold text-tt-navy">Recently updated</div>
              <ul className="pb-2">
                {s.recent.map((d) => (
                  <li key={d.doc_id}>
                    <button onClick={() => onOpen(d.doc_id)} className="group flex w-full items-center gap-2.5 px-5 py-1.5 text-left hover:bg-tt-mist/50">
                      <FileBadge type={d.file_type} size="sm" />
                      <span className="min-w-0 flex-1 truncate text-[12.5px] text-tt-ink">{cleanName(d.file_name)}</span>
                      {d.confidential && <Lock size={12} className="text-[#a8471a]" />}
                      <span className="shrink-0 text-[11.5px] text-tt-slate/70">{timeAgo(d.ingested_at)}</span>
                    </button>
                  </li>
                ))}
              </ul>
            </section>
          </div>
        </div>
      </div>
    </div>
  )
}

const ktokens = (n: number) => (n >= 1000 ? `${Math.round(n / 1000)}k` : String(n))

function PicturesCard({ pics, onStarted }: { pics: ImagesSummary; onStarted: (p: ImagesSummary) => void }) {
  const c = pics.counts
  const pending = c.waiting + c.failed
  const job = pics.job
  const est = pics.estimate
  const [busy, setBusy] = useState(false)

  const describeAll = async () => {
    const cost = est.cost !== null ? ` (about ${est.cost.toFixed(2)})` : ''
    if (!confirm(`Describe all ${pending} waiting pictures with ${pics.vision.deployment}?

Estimated ${ktokens(est.input_tokens + est.output_tokens)} tokens${cost}.`)) return
    setBusy(true)
    try {
      await api.describeImages({})
      onStarted(await api.imagesSummary())
    } catch (e) {
      alert((e as Error).message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="flex flex-wrap items-center gap-x-4 gap-y-2 rounded-xl border border-tt-line bg-white px-5 py-3.5">
      {job.state === 'running' ? (
        <LoaderCircle size={18} className="shrink-0 animate-spin text-tt-electric" />
      ) : pending === 0 ? (
        <Images size={18} className="shrink-0 text-[#0b8f81]" />
      ) : pics.vision.enabled ? (
        <Sparkles size={18} className="shrink-0 text-tt-electric" />
      ) : (
        <Hourglass size={18} className="shrink-0 text-tt-amber" />
      )}
      <div className="min-w-0 flex-1">
        <div className="text-[13.5px] font-semibold text-tt-navy">
          {job.state === 'running'
            ? `Describing pictures… ${job.done ?? 0} of ${job.total ?? 0}`
            : pending
              ? `${pending} picture${pending === 1 ? '' : 's'} waiting to be described`
              : `${c.described} pictures described and searchable`}
        </div>
        <div className="text-[12px] text-tt-slate">
          {c.total} extracted · {c.described} described · {c.skipped} skipped (icons, logos, duplicates)
          {pending > 0 && job.state !== 'running' && ` · about ${ktokens(est.input_tokens + est.output_tokens)} tokens to describe`}
        </div>
      </div>
      {pending > 0 && job.state !== 'running' &&
        (pics.vision.enabled ? (
          <button
            onClick={describeAll}
            disabled={busy}
            className="inline-flex items-center gap-1.5 rounded-lg bg-tt-electric px-3 py-1.5 text-[12.5px] font-semibold text-white hover:bg-tt-electric-600 disabled:opacity-50"
          >
            {busy ? <LoaderCircle size={13} className="animate-spin" /> : <Sparkles size={13} />} Describe all
          </button>
        ) : (
          <span className="text-[12px] text-tt-slate/80">Switches on with the company Azure vision model</span>
        ))}
    </section>
  )
}
