import clsx from 'clsx'
import { ArrowRightLeft, LoaderCircle, Lock, Plus, Search, X } from 'lucide-react'
import { AnimatePresence, motion } from 'motion/react'
import { memo, useEffect, useMemo, useState } from 'react'
import { api } from '../lib/api'
import { domainVisual } from '../lib/domains'
import { cleanName, FileBadge, fileVisual } from '../lib/format'
import type { DocumentInfo, Domain } from '../lib/types'
import { DocDetail } from './DocDetail'
import { LibraryDashboard } from './LibraryDashboard'
import { UploadPanel } from './UploadPanel'

type Props = { docs: DocumentInfo[] | null; onRefresh: () => Promise<void> | void }

const plural = (n: number, word: string) => `${n} ${word}${n === 1 ? '' : 's'}`

/** Something on this file needs a human look (not every processing note: only data that was not captured). */
const needsReview = (d: DocumentInfo) => d.stats?.coverage_percent !== undefined && d.stats.coverage_percent < 99.9

export const ManageView = memo(function ManageView({ docs, onRefresh }: Props) {
  const [domains, setDomains] = useState<Domain[]>([])
  const [q, setQ] = useState('')
  const [domainFilter, setDomainFilter] = useState<string | null>(null)
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [checked, setChecked] = useState<Set<string>>(new Set())
  const [uploadOpen, setUploadOpen] = useState(false)
  const [moving, setMoving] = useState(false)
  const [mobileDetail, setMobileDetail] = useState(false)

  const loadDomains = () => api.domains().then(setDomains).catch(() => {})
  useEffect(() => {
    loadDomains()
  }, [docs])

  const refresh = async () => {
    await onRefresh()
    await loadDomains()
  }

  const shown = useMemo(() => {
    const term = q.trim().toLowerCase()
    return (docs ?? []).filter(
      (d) => (!domainFilter || (d.domain ?? 'unassigned') === domainFilter) && (!term || d.file_name.toLowerCase().includes(term)),
    )
  }, [docs, q, domainFilter])

  // files grouped under their domain, in the registry's order; empty domains listed once at the bottom
  const groups = useMemo(() => {
    const order = [...domains.map((d) => d.id), 'unassigned']
    const by = new Map<string, DocumentInfo[]>()
    for (const d of shown) {
      const id = d.domain ?? 'unassigned'
      by.set(id, [...(by.get(id) ?? []), d])
    }
    return [...by.entries()].sort(([a], [b]) => order.indexOf(a) - order.indexOf(b))
  }, [shown, domains])
  const emptyDomains = q.trim() || domainFilter ? [] : domains.filter((d) => d.id !== 'unassigned' && !(docs ?? []).some((x) => x.domain === d.id))

  // nothing is opened automatically: with no selection the library dashboard is shown
  const selected = (docs ?? []).find((d) => d.doc_id === selectedId) ?? null

  const bulkMove = async (domain: string) => {
    setMoving(true)
    try {
      await api.bulkDomain([...checked], domain)
      setChecked(new Set())
      await refresh()
    } finally {
      setMoving(false)
    }
  }

  const detail = (onDeleted: () => void) =>
    selected && (
      <DocDetail key={selected.doc_id} doc={selected} domains={domains} onChanged={refresh} onDeleted={onDeleted} onClose={() => setSelectedId(null)} />
    )

  return (
    <div className="flex min-h-0 flex-1 bg-tt-canvas">
      {/* library */}
      <div className="flex w-full flex-col border-r border-tt-line bg-white md:w-[300px] md:shrink-0 2xl:w-[340px]">
        <div className="space-y-3 px-4 pt-4 pb-3">
          <div className="flex items-center gap-2">
            <h2 className="font-display text-[15px] font-bold text-tt-navy">Documents</h2>
            {docs && <span className="text-[12.5px] text-tt-slate">{docs.length}</span>}
            <button
              onClick={() => setUploadOpen(true)}
              className="ml-auto inline-flex items-center gap-1.5 rounded-lg bg-tt-electric px-3 py-1.5 text-[12.5px] font-semibold text-white transition hover:bg-tt-electric-600"
            >
              <Plus size={15} /> Add
            </button>
          </div>
          <div className="relative">
            <Search size={15} className="absolute top-1/2 left-3 -translate-y-1/2 text-tt-slate/60" />
            <input
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="Search documents"
              className="w-full rounded-lg border border-tt-line bg-tt-mist/50 py-2 pr-3 pl-9 text-[13px] outline-none transition focus:border-tt-periwinkle focus:bg-white"
            />
          </div>
          {domainFilter && (
            <div className="flex items-center gap-2 text-[12px] text-tt-slate">
              Showing
              <span className="inline-flex items-center gap-1.5 rounded-full bg-tt-mist py-0.5 pr-1 pl-2.5 font-medium text-tt-navy">
                <span className="h-1.5 w-1.5 rounded-full" style={{ background: domainVisual(domainFilter).color }} />
                {domainVisual(domainFilter).label}
                <button onClick={() => setDomainFilter(null)} className="rounded-full p-0.5 text-tt-slate hover:bg-white hover:text-tt-navy" aria-label="Show all domains">
                  <X size={12} />
                </button>
              </span>
            </div>
          )}
        </div>

        <AnimatePresence>
          {checked.size > 0 && (
            <motion.div initial={{ height: 0 }} animate={{ height: 'auto' }} exit={{ height: 0 }} className="overflow-hidden border-y border-tt-line bg-tt-navy text-white">
              <div className="space-y-2 p-3">
                <div className="flex items-center gap-2 text-[12.5px]">
                  <ArrowRightLeft size={14} /> Move <b>{checked.size}</b> file{checked.size === 1 ? '' : 's'} to
                  {moving && <LoaderCircle size={14} className="animate-spin" />}
                  <button onClick={() => setChecked(new Set())} className="ml-auto rounded p-0.5 hover:bg-white/10" aria-label="Clear selection">
                    <X size={14} />
                  </button>
                </div>
                <div className="flex flex-wrap gap-1">
                  {domains.map((d) => (
                    <button key={d.id} disabled={moving} onClick={() => bulkMove(d.id)} className="rounded-md bg-white/10 px-2 py-1 text-[11.5px] font-medium hover:bg-white/20">
                      {d.name}
                    </button>
                  ))}
                </div>
              </div>
            </motion.div>
          )}
        </AnimatePresence>

        <div className="scrollbar-thin flex-1 overflow-y-auto px-2 pb-4">
          {!docs && (
            <div className="flex justify-center py-10">
              <LoaderCircle className="animate-spin text-tt-electric" />
            </div>
          )}
          {docs && shown.length === 0 && (
            <p className="px-3 py-8 text-center text-[13px] text-tt-slate">{q.trim() ? 'No documents match your search.' : 'No documents yet.'}</p>
          )}

          {groups.map(([domainId, ds]) => {
            const v = domainVisual(domainId)
            return (
              <div key={domainId} className="mt-2 first:mt-0">
                <div className="flex items-center gap-2 px-2.5 pt-2 pb-1.5">
                  <span className="h-1.5 w-1.5 rounded-full" style={{ background: v.color }} />
                  <span className="text-[11.5px] font-semibold text-tt-slate">{v.label}</span>
                  <span className="text-[11.5px] text-tt-slate/60">{ds.length}</span>
                </div>
                {ds.map((d) => {
                  const active = d.doc_id === selectedId
                  return (
                    <div
                      key={d.doc_id}
                      onClick={() => {
                        setSelectedId(d.doc_id)
                        if (!window.matchMedia('(min-width: 768px)').matches) setMobileDetail(true)
                      }}
                      className={clsx(
                        'group relative flex cursor-pointer items-center gap-2.5 rounded-lg px-2.5 py-2 transition',
                        active ? 'bg-tt-electric/[0.06]' : 'hover:bg-tt-mist/70',
                      )}
                    >
                      {active && <span className="absolute inset-y-2 left-0 w-[3px] rounded-full bg-tt-electric" />}
                      <span className="relative">
                        <FileBadge type={d.file_type} size="sm" />
                        <input
                          type="checkbox"
                          checked={checked.has(d.doc_id)}
                          onClick={(e) => e.stopPropagation()}
                          onChange={(e) =>
                            setChecked((cur) => {
                              const next = new Set(cur)
                              if (e.target.checked) next.add(d.doc_id)
                              else next.delete(d.doc_id)
                              return next
                            })
                          }
                          className={clsx(
                            'absolute inset-0 m-auto h-4 w-4 cursor-pointer accent-[#0000b3] transition',
                            checked.size ? 'opacity-100' : 'opacity-0 group-hover:opacity-100',
                          )}
                          aria-label={`Select ${d.file_name}`}
                          title="Select to move several files at once"
                        />
                      </span>
                      <div className="min-w-0 flex-1">
                        <div className={clsx('truncate text-[13px]', active ? 'font-semibold text-tt-navy' : 'font-medium text-tt-ink')} title={d.file_name}>
                          {cleanName(d.file_name)}
                        </div>
                        <div className="text-[11.5px] text-tt-slate">
                          {fileVisual(d.file_type).label} · {d.records ? plural(d.records, 'record') : plural(d.chunks, 'chunk')}
                        </div>
                      </div>
                      {d.confidential && (
                        <span title="Confidential: super users and developers only">
                          <Lock size={13} className="text-[#a8471a]" />
                        </span>
                      )}
                      {needsReview(d) && (
                        <span className="h-2 w-2 shrink-0 rounded-full bg-tt-amber" title={`${d.stats.coverage_percent}% of the data captured — worth a look`} />
                      )}
                    </div>
                  )
                })}
              </div>
            )
          })}

          {emptyDomains.length > 0 && (
            <p className="mx-2.5 mt-4 border-t border-tt-line pt-3 text-[11.5px] leading-relaxed text-tt-slate/80">
              No documents yet in {emptyDomains.map((d) => d.name).join(', ')}.
            </p>
          )}
        </div>
      </div>

      {/* detail */}
      <div className="hidden min-w-0 flex-1 md:block">
        {selected ? (
          detail(() => {
            setSelectedId(null)
            refresh()
          })
        ) : docs ? (
          <LibraryDashboard docs={docs} domains={domains} onOpen={setSelectedId} onDomain={setDomainFilter} onAdd={() => setUploadOpen(true)} />
        ) : (
          <div className="flex h-full items-center justify-center">
            <LoaderCircle className="animate-spin text-tt-electric" />
          </div>
        )}
      </div>

      {mobileDetail && selected && (
        <div className="fixed inset-0 z-40 flex flex-col bg-white md:hidden">
          <button onClick={() => setMobileDetail(false)} className="flex items-center gap-1.5 border-b border-tt-line px-4 py-3 text-left text-[13px] font-semibold text-tt-electric">
            <X size={15} /> Back to documents
          </button>
          <div className="min-h-0 flex-1">
            {detail(() => {
              setMobileDetail(false)
              setSelectedId(null)
              refresh()
            })}
          </div>
        </div>
      )}

      <AnimatePresence>
        {uploadOpen && (
          <>
            <motion.div className="fixed inset-0 z-40 bg-tt-midnight/50" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} onClick={() => setUploadOpen(false)} />
            <motion.div
              className="fixed inset-x-3 top-[7vh] z-50 mx-auto max-h-[86vh] max-w-2xl overflow-y-auto rounded-2xl"
              initial={{ opacity: 0, y: 16 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: 16 }}
              transition={{ duration: 0.18 }}
            >
              <UploadPanel domains={domains} defaultDomain="" onClose={() => setUploadOpen(false)} onDone={refresh} />
            </motion.div>
          </>
        )}
      </AnimatePresence>
    </div>
  )
})
