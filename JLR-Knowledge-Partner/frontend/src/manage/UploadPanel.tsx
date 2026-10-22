import clsx from 'clsx'
import { ArrowRightLeft, ChevronRight, CircleCheck, CloudUpload, LoaderCircle, Plus, RefreshCw, TriangleAlert, X } from 'lucide-react'
import { AnimatePresence, motion } from 'motion/react'
import { useRef, useState } from 'react'
import { api } from '../lib/api'
import { domainVisual } from '../lib/domains'
import { bytes, extOf, FileBadge } from '../lib/format'
import type { Domain, IngestResult } from '../lib/types'

const ACCEPT = ['.xlsx', '.xlsm', '.csv', '.pdf', '.docx', '.pptx', '.txt', '.md']
const DOC_TYPES = ['Benchmarking', 'Design guideline', 'FMEA', 'Control plan', 'Specification', 'Issue log', 'Lessons learned', 'Other']

type Item = { id: string; file: File; state: 'queued' | 'uploading' | 'done'; result?: IngestResult }
type Field = { key: string; value: string }

type Props = { domains: Domain[]; defaultDomain: string; onDone: () => void; onClose: () => void }

export function UploadPanel({ domains, defaultDomain, onDone, onClose }: Props) {
  const [items, setItems] = useState<Item[]>([])
  const [domain, setDomain] = useState(defaultDomain)
  const [drag, setDrag] = useState(false)
  const [running, setRunning] = useState(false)
  const [project, setProject] = useState('')
  const [docType, setDocType] = useState('')
  const [department, setDepartment] = useState('')
  const [tags, setTags] = useState('')
  const [custom, setCustom] = useState<Field[]>([])
  const [force, setForce] = useState(false)
  const input = useRef<HTMLInputElement>(null)

  const add = (files: FileList | null) => {
    if (!files) return
    const next = Array.from(files)
      .filter((f) => ACCEPT.includes(`.${extOf(f.name)}`))
      .map((file) => ({ id: `${file.name}-${file.size}-${file.lastModified}`, file, state: 'queued' as const }))
    setItems((cur) => [...cur.filter((c) => c.state !== 'done'), ...next.filter((n) => !cur.some((c) => c.id === n.id))])
  }

  const meta = () => {
    const m: Record<string, unknown> = {}
    if (project.trim()) m.project = project.trim()
    if (docType) m.doc_type = docType
    if (department.trim()) m.department = department.trim()
    const t = tags.split(',').map((x) => x.trim()).filter(Boolean)
    if (t.length) m.tags = t
    for (const f of custom) if (f.key.trim() && f.value.trim()) m[f.key.trim()] = f.value.trim()
    return m
  }

  const run = async () => {
    setRunning(true)
    const m = meta()
    for (const it of items.filter((i) => i.state === 'queued')) {
      setItems((cur) => cur.map((c) => (c.id === it.id ? { ...c, state: 'uploading' } : c)))
      let result: IngestResult
      try {
        result = await api.upload(it.file, m, force, domain)
      } catch (e) {
        result = { file_name: it.file.name, status: 'failed', error: (e as Error).message, seconds: 0 }
      }
      setItems((cur) => cur.map((c) => (c.id === it.id ? { ...c, state: 'done', result } : c)))
    }
    setRunning(false)
    onDone()
  }

  const queued = items.filter((i) => i.state === 'queued').length
  const allDone = items.length > 0 && items.every((i) => i.state === 'done')
  const input_ = 'w-full rounded-lg border border-tt-line bg-white px-3 py-2 text-[13px] outline-none transition focus:border-tt-periwinkle focus:ring-4 focus:ring-tt-periwinkle/15'
  const step = 'flex h-5 w-5 items-center justify-center rounded-full bg-tt-navy text-[11px] font-bold text-white'

  return (
    <section className="rounded-2xl bg-white shadow-lift">
      <div className="flex items-start gap-3 border-b border-tt-line px-6 pt-5 pb-4">
        <div className="min-w-0 flex-1">
          <h2 className="font-display text-[17px] font-bold text-tt-navy">Add documents</h2>
          <p className="mt-0.5 text-[12.5px] text-tt-slate">The assistant can answer from them as soon as processing finishes.</p>
        </div>
        <button onClick={onClose} className="rounded-lg p-1.5 text-tt-slate hover:bg-tt-mist" aria-label="Close">
          <X size={18} />
        </button>
      </div>

      <div className="space-y-5 px-6 py-5">
        {/* 1. domain */}
        <div>
          <div className="mb-2.5 flex items-center gap-2 text-[13px] font-semibold text-tt-navy">
            <span className={step}>1</span> Choose a domain
          </div>
          <div className="flex flex-wrap gap-1.5">
            {domains.map((d) => {
              const on = domain === d.id
              return (
                <button
                  key={d.id}
                  onClick={() => setDomain(d.id)}
                  className={clsx(
                    'inline-flex items-center gap-2 rounded-full border px-3 py-1.5 text-[12.5px] font-medium transition',
                    on ? 'border-tt-electric bg-tt-electric/[0.06] text-tt-navy' : 'border-tt-line text-tt-slate hover:border-tt-periwinkle hover:text-tt-navy',
                  )}
                >
                  <span className="h-2 w-2 rounded-full" style={{ background: domainVisual(d.id).color }} />
                  {d.name}
                  {on && <CircleCheck size={14} className="text-tt-electric" />}
                </button>
              )
            })}
          </div>
        </div>

        {/* 2. files */}
        <div>
          <div className="mb-2.5 flex items-center gap-2 text-[13px] font-semibold text-tt-navy">
            <span className={step}>2</span> Add files
          </div>
          <div
            onDragOver={(e) => {
              e.preventDefault()
              setDrag(true)
            }}
            onDragLeave={() => setDrag(false)}
            onDrop={(e) => {
              e.preventDefault()
              setDrag(false)
              add(e.dataTransfer.files)
            }}
            onClick={() => input.current?.click()}
            className={clsx(
              'flex cursor-pointer items-center gap-4 rounded-xl border-2 border-dashed px-5 py-5 transition',
              drag ? 'border-tt-electric bg-tt-electric/[0.04]' : 'border-tt-line hover:border-tt-periwinkle hover:bg-tt-mist/40',
            )}
          >
            <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-tt-electric/[0.07] text-tt-electric">
              <CloudUpload size={22} />
            </div>
            <div>
              <p className="text-[13.5px] font-semibold text-tt-navy">
                Drop files here or <span className="text-tt-electric underline-offset-2 hover:underline">browse</span>
              </p>
              <p className="mt-0.5 text-[12px] text-tt-slate">Excel, PDF, Word, PowerPoint, CSV or text</p>
            </div>
            <input ref={input} type="file" multiple accept={ACCEPT.join(',')} className="hidden" onChange={(e) => add(e.target.files)} />
          </div>

          {items.length > 0 && (
            <div className="mt-2.5 divide-y divide-tt-line rounded-xl border border-tt-line">
              <AnimatePresence initial={false}>
                {items.map((it) => {
                  const r = it.result
                  return (
                    <motion.div key={it.id} initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0, height: 0 }} className="flex items-center gap-3 px-3 py-2.5">
                      <FileBadge type={extOf(it.file.name)} size="sm" />
                      <div className="min-w-0 flex-1">
                        <div className="truncate text-[13px] font-medium text-tt-ink">{it.file.name}</div>
                        <div className={clsx('text-[11.5px]', r?.status === 'failed' ? 'text-[#a8401a]' : 'text-tt-slate')}>
                          {it.state === 'queued' && bytes(it.file.size)}
                          {it.state === 'uploading' && 'Processing…'}
                          {r?.status === 'indexed' && `Added · ${r.records ? `${r.records} records` : `${r.chunks} chunks`} · ${r.seconds}s`}
                          {r?.status === 'skipped' && 'Already in the library, unchanged'}
                          {r?.status === 'reclassified' && 'Already in the library, moved to this domain'}
                          {r?.status === 'failed' && r.error}
                        </div>
                      </div>
                      {it.state === 'queued' && (
                        <button onClick={() => setItems((c) => c.filter((x) => x.id !== it.id))} className="rounded-md p-1 text-tt-slate hover:bg-tt-mist" aria-label="Remove">
                          <X size={14} />
                        </button>
                      )}
                      {it.state === 'uploading' && <LoaderCircle size={17} className="animate-spin text-tt-electric" />}
                      {r?.status === 'indexed' && <CircleCheck size={18} className="text-[#0b8f81]" />}
                      {r?.status === 'skipped' && <RefreshCw size={16} className="text-tt-slate" />}
                      {r?.status === 'reclassified' && <ArrowRightLeft size={16} className="text-tt-electric" />}
                      {r?.status === 'failed' && <TriangleAlert size={17} className="text-tt-ember" />}
                    </motion.div>
                  )
                })}
              </AnimatePresence>
            </div>
          )}
        </div>

        {/* optional */}
        <details className="group rounded-xl border border-tt-line">
          <summary className="flex cursor-pointer list-none items-center gap-1.5 px-4 py-2.5 text-[12.5px] font-semibold text-tt-slate select-none hover:text-tt-navy">
            <ChevronRight size={14} className="transition group-open:rotate-90" /> Optional details
            <span className="font-normal text-tt-slate/70">project, document type, tags</span>
          </summary>
          <div className="space-y-3 border-t border-tt-line px-4 py-4">
            <div className="grid gap-3 sm:grid-cols-2">
              <label className="block">
                <span className="mb-1 block text-[12px] font-medium text-tt-slate">Project</span>
                <input value={project} onChange={(e) => setProject(e.target.value)} className={input_} placeholder="e.g. EDS" />
              </label>
              <label className="block">
                <span className="mb-1 block text-[12px] font-medium text-tt-slate">Document type</span>
                <select value={docType} onChange={(e) => setDocType(e.target.value)} className={input_}>
                  <option value="">Not specified</option>
                  {DOC_TYPES.map((d) => (
                    <option key={d}>{d}</option>
                  ))}
                </select>
              </label>
              <label className="block">
                <span className="mb-1 block text-[12px] font-medium text-tt-slate">Department or area</span>
                <input value={department} onChange={(e) => setDepartment(e.target.value)} className={input_} placeholder="e.g. Body Exterior" />
              </label>
              <label className="block">
                <span className="mb-1 block text-[12px] font-medium text-tt-slate">Tags (comma separated)</span>
                <input value={tags} onChange={(e) => setTags(e.target.value)} className={input_} placeholder="sensor, bumper" />
              </label>
            </div>
            {custom.map((f, i) => (
              <div key={i} className="flex gap-2">
                <input
                  value={f.key}
                  onChange={(e) => setCustom((c) => c.map((x, j) => (j === i ? { ...x, key: e.target.value } : x)))}
                  className={clsx(input_, 'w-2/5')}
                  placeholder="Field"
                />
                <input
                  value={f.value}
                  onChange={(e) => setCustom((c) => c.map((x, j) => (j === i ? { ...x, value: e.target.value } : x)))}
                  className={input_}
                  placeholder="Value"
                />
                <button onClick={() => setCustom((c) => c.filter((_, j) => j !== i))} className="rounded-lg px-2 text-tt-slate hover:bg-tt-mist" aria-label="Remove field">
                  <X size={15} />
                </button>
              </div>
            ))}
            <div className="flex flex-wrap items-center justify-between gap-3">
              <button
                onClick={() => setCustom((c) => [...c, { key: '', value: '' }])}
                className="inline-flex items-center gap-1.5 rounded-md px-1.5 py-1 text-[12.5px] font-medium text-tt-electric hover:bg-tt-electric/[0.06]"
              >
                <Plus size={14} /> Add field
              </button>
              <label className="flex cursor-pointer items-center gap-2 text-[12.5px] text-tt-slate select-none">
                <input type="checkbox" checked={force} onChange={(e) => setForce(e.target.checked)} className="h-3.5 w-3.5 accent-[#0000b3]" />
                Process again even if the file is unchanged
              </label>
            </div>
          </div>
        </details>
      </div>

      <div className="flex items-center justify-end gap-2 rounded-b-2xl border-t border-tt-line bg-tt-mist/40 px-6 py-3.5">
        {!domain && queued > 0 && <span className="mr-auto text-[12px] text-tt-slate">Choose a domain to continue</span>}
        <button onClick={onClose} className="rounded-lg px-4 py-2 text-[13px] font-semibold text-tt-slate hover:bg-white hover:text-tt-navy">
          {allDone ? 'Done' : 'Cancel'}
        </button>
        <button
          onClick={run}
          disabled={!queued || running || !domain}
          className="inline-flex items-center gap-2 rounded-lg bg-tt-electric px-4 py-2 text-[13px] font-semibold text-white transition hover:bg-tt-electric-600 disabled:opacity-40"
        >
          {running && <LoaderCircle size={15} className="animate-spin" />}
          {running ? 'Adding…' : queued ? `Add ${queued} file${queued === 1 ? '' : 's'}` : 'Add files'}
        </button>
      </div>
    </section>
  )
}
