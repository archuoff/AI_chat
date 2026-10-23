import clsx from 'clsx'
import { ArrowRightLeft, ChevronRight, CircleCheck, CloudUpload, History, LoaderCircle, Plus, RefreshCw, Sparkles, TriangleAlert, X } from 'lucide-react'
import { AnimatePresence, motion } from 'motion/react'
import { useEffect, useRef, useState } from 'react'
import { api } from '../lib/api'
import { domainVisual } from '../lib/domains'
import { bytes, extOf, FileBadge } from '../lib/format'
import type { DocRef, Domain, IngestResult, SigSize, UploadCheck } from '../lib/types'

const ACCEPT = ['.xlsx', '.xlsm', '.csv', '.pdf', '.docx', '.pptx', '.txt', '.md']
const DOC_TYPES = ['Benchmarking', 'Design guideline', 'FMEA', 'Control plan', 'Specification', 'Issue log', 'Lessons learned', 'Other']

type Item = {
  id: string
  file: File
  /** queued -> checking (read once, look for similar documents) -> checked (SME decides) -> uploading -> done */
  state: 'queued' | 'checking' | 'checked' | 'unreadable' | 'uploading' | 'done'
  check?: UploadCheck
  intent: 'new' | 'update'
  replaces: string
  allowDuplicate: boolean
  error?: string
  result?: IngestResult
}
type Field = { key: string; value: string }

const pct = (n: number) => `${n.toLocaleString('en-GB')}`

/** The new file is much smaller than the document it would replace: everything else would be hidden. */
function partialWarning(old: SigSize | null | undefined, next: SigSize): string | null {
  if (!old) return null
  if (old.unit && old.unit === next.unit && old.units >= 2 && next.units < old.units * 0.5)
    return `The existing document has ${old.units} ${old.unit}, this file only ${next.units}. Whatever is missing would no longer be searchable.`
  const was = old.records + old.text_blocks
  const now = next.records + next.text_blocks
  if (was >= 10 && now < was * 0.5) return `The existing document has ${pct(was)} items, this file only ${pct(now)}. Whatever is missing would no longer be searchable.`
  return null
}

/** What stops this file from being added yet (null = ready). */
function blocker(it: Item): string | null {
  const c = it.check
  if (!c) return 'Still being checked'
  if (it.intent === 'update') {
    if (!it.replaces) return 'Choose the document this file updates'
    if (c.same_name && c.same_name.doc_id !== it.replaces) return `A different document is already named "${c.same_name.file_name}": rename the file or update that one`
  } else if (c.same_name) return `A document named "${c.same_name.file_name}" already exists: choose Update, or rename the file`
  if (c.exact.length && !it.allowDuplicate) return 'This exact file is already in the library: tick "Add anyway" to continue'
  return null
}

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
      .map((file) => ({
        id: `${file.name}-${file.size}-${file.lastModified}`,
        file,
        state: 'queued' as const,
        intent: 'new' as const,
        replaces: '',
        allowDuplicate: false,
      }))
    setItems((cur) => [...cur.filter((c) => c.state !== 'done'), ...next.filter((n) => !cur.some((c) => c.id === n.id))])
  }

  const patch = (id: string, change: Partial<Item>) => setItems((cur) => cur.map((c) => (c.id === id ? { ...c, ...change } : c)))

  // files are checked one at a time (reading a big workbook takes a moment)
  useEffect(() => {
    if (items.some((i) => i.state === 'checking')) return
    const next = items.find((i) => i.state === 'queued')
    if (!next) return
    patch(next.id, { state: 'checking', error: undefined })
    api
      .checkUpload(next.file, domain)
      .then((check) => {
        const top = check.suggestions[0]
        // pre-select "update" only when the system is sure; otherwise the SME picks
        const update = top?.label === 'likely' && !check.exact.some((e) => !e.superseded)
        patch(next.id, { state: 'checked', check, intent: update ? 'update' : 'new', replaces: update ? top.doc_id : '' })
      })
      .catch((e: Error) => patch(next.id, { state: 'unreadable', error: e.message }))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [items])

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
    for (const it of items.filter((i) => i.state === 'checked' && !blocker(i))) {
      patch(it.id, { state: 'uploading', error: undefined })
      try {
        const result = await api.commitUpload({
          check_id: it.check!.check_id,
          intent: it.intent,
          replaces: it.intent === 'update' ? it.replaces : undefined,
          domain,
          metadata: m,
          force,
          allow_duplicate: it.allowDuplicate,
        })
        if (result.status === 'failed') patch(it.id, { state: 'checked', error: result.error ?? 'Processing failed' })
        else patch(it.id, { state: 'done', result })
      } catch (e) {
        patch(it.id, { state: 'checked', error: (e as Error).message })
      }
    }
    setRunning(false)
    onDone()
  }

  const ready = items.filter((i) => i.state === 'checked' && !blocker(i)).length
  const waiting = items.filter((i) => i.state === 'queued' || i.state === 'checking').length
  const queued = ready
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
                  const removable = it.state === 'queued' || it.state === 'checked' || it.state === 'unreadable'
                  return (
                    <motion.div key={it.id} initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0, height: 0 }} className="px-3 py-2.5">
                      <div className="flex items-center gap-3">
                        <FileBadge type={extOf(it.file.name)} size="sm" />
                        <div className="min-w-0 flex-1">
                          <div className="truncate text-[13px] font-medium text-tt-ink">{it.file.name}</div>
                          <div className={clsx('text-[11.5px]', r?.status === 'failed' || it.state === 'unreadable' ? 'text-[#a8401a]' : 'text-tt-slate')}>
                            {it.state === 'queued' && `${bytes(it.file.size)} · waiting to be checked`}
                            {it.state === 'checking' && 'Reading the file and looking for similar documents…'}
                            {it.state === 'checked' && bytes(it.file.size)}
                            {it.state === 'unreadable' && it.error}
                            {it.state === 'uploading' && 'Processing…'}
                            {r?.status === 'indexed' &&
                              `${r.replaced ? 'Updated' : 'Added'} · ${r.records ? `${r.records} records` : `${r.chunks} chunks`} · ${r.seconds}s`}
                            {r?.status === 'skipped' && 'Already in the library, unchanged'}
                            {r?.status === 'reclassified' && 'Already in the library, moved to this domain'}
                            {r?.status === 'failed' && r.error}
                          </div>
                        </div>
                        {removable && (
                          <button onClick={() => setItems((c) => c.filter((x) => x.id !== it.id))} className="rounded-md p-1 text-tt-slate hover:bg-tt-mist" aria-label="Remove">
                            <X size={14} />
                          </button>
                        )}
                        {(it.state === 'checking' || it.state === 'uploading') && <LoaderCircle size={17} className="animate-spin text-tt-electric" />}
                        {it.state === 'unreadable' && <TriangleAlert size={17} className="text-tt-ember" />}
                        {r?.status === 'indexed' && <CircleCheck size={18} className="text-[#0b8f81]" />}
                        {r?.status === 'skipped' && <RefreshCw size={16} className="text-tt-slate" />}
                        {r?.status === 'reclassified' && <ArrowRightLeft size={16} className="text-tt-electric" />}
                        {r?.status === 'failed' && <TriangleAlert size={17} className="text-tt-ember" />}
                      </div>
                      {r?.replaced && (
                        <p className="mt-1.5 ml-11 flex items-center gap-1.5 text-[12px] text-tt-slate">
                          <History size={13} /> "{r.replaced.file_name}" is hidden from the assistant. You can restore it from the document page.
                        </p>
                      )}
                      {it.state === 'checked' && it.check && <Decision it={it} domains={domains} onChange={(change) => patch(it.id, change)} />}
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
        {!domain && items.length > 0 && <span className="mr-auto text-[12px] text-tt-slate">Choose a domain to continue</span>}
        {domain && waiting > 0 && <span className="mr-auto text-[12px] text-tt-slate">Checking {waiting} file{waiting === 1 ? '' : 's'}…</span>}
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

const label = (domains: Domain[], id: string) => domains.find((d) => d.id === id)?.name ?? id

/** Per file: what the system found in the library, and the SME's choice (new document / update of ...). */
function Decision({ it, domains, onChange }: { it: Item; domains: Domain[]; onChange: (change: Partial<Item>) => void }) {
  const c = it.check!
  const live = c.exact.filter((e) => !e.superseded)
  const hidden = c.exact.filter((e) => e.superseded)
  const chosen: DocRef | undefined = c.others.find((o) => o.doc_id === it.replaces)
  const partial = it.intent === 'update' ? partialWarning(chosen?.sig_size, c.size) : null
  const stop = blocker(it)
  const suggested = new Set(c.suggestions.map((s) => s.doc_id))
  const radio = 'h-3.5 w-3.5 accent-[#0000b3]'

  return (
    <div className="mt-2.5 ml-11 space-y-2.5">
      {(live.length > 0 || hidden.length > 0) && (
        <div className="rounded-lg border border-[#f1d9a6] bg-[#fff8e8] px-3 py-2 text-[12px] text-[#7a5410]">
          <div className="flex items-start gap-2">
            <TriangleAlert size={14} className="mt-0.5 shrink-0" />
            <div className="min-w-0">
              {live.map((e) => (
                <p key={e.doc_id}>
                  This exact file is already in the library as <b>{e.file_name}</b> ({label(domains, e.domain)}).
                </p>
              ))}
              {hidden.map((e) => (
                <p key={e.doc_id}>
                  This exact file is the older version <b>{e.file_name}</b>, replaced by a newer one. Add it again only if that is intended.
                </p>
              ))}
              <label className="mt-1 flex cursor-pointer items-center gap-2 select-none">
                <input type="checkbox" checked={it.allowDuplicate} onChange={(e) => onChange({ allowDuplicate: e.target.checked })} className={radio} />
                Add anyway
              </label>
            </div>
          </div>
        </div>
      )}

      {c.suggestions.length > 0 && (
        <div>
          <div className="mb-1 flex items-center gap-1.5 text-[11.5px] font-semibold tracking-wide text-tt-slate uppercase">
            <Sparkles size={12} /> Similar documents already in the library
          </div>
          <div className="space-y-1">
            {c.suggestions.map((s) => {
              const on = it.intent === 'update' && it.replaces === s.doc_id
              return (
                <button
                  key={s.doc_id}
                  onClick={() => onChange({ intent: 'update', replaces: s.doc_id })}
                  className={clsx(
                    'flex w-full items-start gap-2 rounded-lg border px-2.5 py-1.5 text-left transition',
                    on ? 'border-tt-electric bg-tt-electric/[0.05]' : 'border-tt-line hover:border-tt-periwinkle hover:bg-tt-mist/40',
                  )}
                >
                  <span
                    className={clsx(
                      'mt-0.5 shrink-0 rounded px-1.5 py-px text-[10.5px] font-semibold',
                      s.label === 'likely' ? 'bg-[#e3f6f2] text-[#0b6f64]' : 'bg-tt-mist text-tt-slate',
                    )}
                  >
                    {s.label === 'likely' ? 'Likely update' : 'Related'}
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-[12.5px] font-medium text-tt-ink">{s.file_name}</span>
                    <span className="block text-[11.5px] text-tt-slate">
                      {label(domains, s.domain)} · {s.reasons.filter((x) => x !== 'same domain').join(' · ') || 'similar'}
                    </span>
                  </span>
                </button>
              )
            })}
          </div>
        </div>
      )}

      <div className="space-y-1.5 text-[12.5px] text-tt-navy">
        <label className="flex cursor-pointer items-center gap-2 select-none">
          <input type="radio" name={`intent-${it.id}`} checked={it.intent === 'new'} onChange={() => onChange({ intent: 'new', replaces: '' })} className={radio} />
          New document
        </label>
        <div className="flex flex-wrap items-center gap-2">
          <label className="flex cursor-pointer items-center gap-2 select-none">
            <input type="radio" name={`intent-${it.id}`} checked={it.intent === 'update'} onChange={() => onChange({ intent: 'update' })} className={radio} />
            Update of
          </label>
          <select
            value={it.replaces}
            onChange={(e) => onChange({ intent: 'update', replaces: e.target.value })}
            className="min-w-0 max-w-full flex-1 rounded-lg border border-tt-line bg-white px-2.5 py-1.5 text-[12.5px] outline-none focus:border-tt-periwinkle"
          >
            <option value="">Choose a document…</option>
            {c.suggestions.length > 0 && (
              <optgroup label="Suggested">
                {c.suggestions.map((s) => (
                  <option key={s.doc_id} value={s.doc_id}>
                    {s.file_name} · {label(domains, s.domain)}
                  </option>
                ))}
              </optgroup>
            )}
            <optgroup label="All documents">
              {c.others
                .filter((o) => !suggested.has(o.doc_id))
                .map((o) => (
                  <option key={o.doc_id} value={o.doc_id}>
                    {o.file_name} · {label(domains, o.domain)}
                  </option>
                ))}
            </optgroup>
          </select>
        </div>
        {it.intent === 'update' && (
          <p className="ml-5 text-[11.5px] text-tt-slate">The old version is hidden from the assistant, not deleted. You can restore it any time.</p>
        )}
      </div>

      {partial && (
        <p className="flex items-start gap-1.5 text-[12px] text-[#a8401a]">
          <TriangleAlert size={14} className="mt-0.5 shrink-0" /> {partial}
        </p>
      )}
      {c.unchecked > 0 && (
        <p className="text-[11.5px] text-tt-slate">
          {c.unchecked} document{c.unchecked === 1 ? '' : 's'} could only be compared by name (content data not built yet).
        </p>
      )}
      {(it.error || stop) && (
        <p className={clsx('text-[12px]', it.error ? 'text-[#a8401a]' : 'text-tt-slate')}>{it.error ?? stop}</p>
      )}
    </div>
  )
}
