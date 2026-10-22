import clsx from 'clsx'
import { Check, ChevronDown, CircleCheck, Ellipsis, LoaderCircle, Lock, LockOpen, RefreshCw, Trash, WandSparkles, X } from 'lucide-react'
import { AnimatePresence, motion } from 'motion/react'
import { type ReactNode, useCallback, useEffect, useState } from 'react'
import { api } from '../lib/api'
import { domainVisual } from '../lib/domains'
import { bytes, cleanName, FileBadge, fileVisual, timeAgo } from '../lib/format'
import type { DocumentInfo, Domain, DomainSuggestion, ExcelPreview, ParseOptions } from '../lib/types'
import { ChunksTab } from './ChunksTab'
import { ImagesTab } from './ImagesTab'
import { normalize, optionsEqual } from './excel'
import { OverviewTab } from './OverviewTab'
import { RecordsTab } from './RecordsTab'
import { SheetPreview } from './SheetPreview'

type Tab = 'overview' | 'preview' | 'records' | 'images' | 'chunks'
type Props = { doc: DocumentInfo; domains: Domain[]; onChanged: () => Promise<void> | void; onDeleted: () => void; onClose: () => void }

export function DocDetail({ doc, domains, onChanged, onDeleted, onClose }: Props) {
  const isExcel = doc.file_type === 'xlsx' || doc.file_type === 'xlsm'
  const [tab, setTab] = useState<Tab>('overview')
  const [sheet, setSheet] = useState<string | undefined>(undefined)
  const [preview, setPreview] = useState<ExcelPreview | null>(null)
  const [previewLoading, setPreviewLoading] = useState(false)
  const [previewError, setPreviewError] = useState<string | null>(null)
  const [draft, setDraft] = useState<ParseOptions>(doc.parse_options ?? {})
  const [busy, setBusy] = useState<null | 'apply' | 'reprocess' | 'delete' | 'domain' | 'suggest' | 'access'>(null)
  const [toast, setToast] = useState<{ kind: 'ok' | 'err'; text: string } | null>(null)
  const [suggestion, setSuggestion] = useState<DomainSuggestion | null>(null)
  const [menu, setMenu] = useState<null | 'domain' | 'more'>(null)

  // new document selected: reset everything
  useEffect(() => {
    setTab('overview')
    setSheet(undefined)
    setPreview(null)
    setPreviewError(null)
    setSuggestion(null)
    setToast(null)
  }, [doc.doc_id])

  useEffect(() => setDraft(doc.parse_options ?? {}), [doc.doc_id, doc.parse_options])

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== 'Escape' || menu || document.querySelector('.fixed.z-50')) return
      const t = e.target as HTMLElement
      if (t.closest('input, textarea, select')) return
      onClose()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [menu, onClose])

  const loadPreview = useCallback(() => {
    if (!isExcel) return
    setPreviewLoading(true)
    setPreviewError(null)
    api
      .excelPreview(doc.doc_id, sheet)
      .then((p) => setPreview(p))
      .catch((e: Error) => setPreviewError(e.message))
      .finally(() => setPreviewLoading(false))
  }, [doc.doc_id, isExcel, sheet])

  useEffect(() => {
    if (isExcel && (tab === 'preview' || tab === 'records')) loadPreview()
  }, [tab, loadPreview, isExcel, doc.ingested_at])

  useEffect(() => {
    if (!toast) return
    const t = setTimeout(() => setToast(null), 5000)
    return () => clearTimeout(t)
  }, [toast])

  const run = async (kind: NonNullable<typeof busy>, fn: () => Promise<string | void>) => {
    setBusy(kind)
    try {
      const msg = await fn()
      if (msg) setToast({ kind: 'ok', text: msg })
    } catch (e) {
      setToast({ kind: 'err', text: (e as Error).message })
    } finally {
      setBusy(null)
    }
  }

  const setDomain = (domain: string) =>
    run('domain', async () => {
      setMenu(null)
      await api.setDomain(doc.doc_id, domain)
      await onChanged()
      setSuggestion(null)
      return `Moved to ${domainVisual(domain).label}`
    })

  const pending = !optionsEqual(draft, doc.parse_options)
  const pendingCount = Object.keys(normalize(draft).tables ?? {}).length + Object.keys(normalize(draft).sheets ?? {}).length

  const apply = () =>
    run('apply', async () => {
      const r = await api.saveParseOptions(doc.doc_id, normalize(draft))
      await onChanged()
      return `Changes applied: ${r.records ?? 0} records stored (${r.seconds}s)`
    })

  const tabs: { id: Tab; label: string; show: boolean; count?: number }[] = [
    { id: 'overview', label: 'Overview', show: true },
    { id: 'preview', label: 'Sheet preview', show: isExcel },
    { id: 'records', label: 'Records', show: isExcel, count: doc.records },
    { id: 'images', label: 'Pictures', show: (doc.images?.total ?? 0) > 0, count: doc.images?.total },
    { id: 'chunks', label: 'Search chunks', show: true, count: doc.chunks },
  ]
  const dv = domainVisual(doc.domain)

  return (
    <div className="relative flex h-full min-h-0 flex-col">
      {/* header */}
      <div className="border-b border-tt-line bg-white px-5 pt-4 sm:px-6">
        <div className="flex flex-wrap items-center gap-3">
          <FileBadge type={doc.file_type} size="lg" />
          <div className="min-w-0 flex-1">
            <h2 className="truncate font-display text-[16.5px] font-bold text-tt-navy" title={doc.file_name}>
              {cleanName(doc.file_name)}
            </h2>
            <p className="text-[12.5px] text-tt-slate">
              {fileVisual(doc.file_type).label} · {bytes(doc.size_bytes)} · updated {timeAgo(doc.ingested_at)}
            </p>
          </div>

          <div className="flex items-center gap-1.5">
            {/* domain (with AI suggestion) */}
            <div className="relative">
              <button
                onClick={() => setMenu((m) => (m === 'domain' ? null : 'domain'))}
                className="inline-flex items-center gap-2 rounded-lg border border-tt-line bg-white py-1.5 pr-2 pl-2.5 text-[12.5px] font-semibold text-tt-navy transition hover:border-tt-periwinkle"
                title="Domain this document belongs to"
              >
                <span className="h-2 w-2 rounded-full" style={{ background: dv.color }} />
                {dv.label}
                {busy === 'domain' || busy === 'suggest' ? <LoaderCircle size={14} className="animate-spin text-tt-slate" /> : <ChevronDown size={14} className="text-tt-slate" />}
              </button>
              {menu === 'domain' && (
                <Menu onClose={() => setMenu(null)}>
                  <div className="px-2.5 pt-1.5 pb-1 text-[11px] font-semibold text-tt-slate/80">Move to</div>
                  {domains.map((d) => (
                    <button
                      key={d.id}
                      onClick={() => d.id !== doc.domain && setDomain(d.id)}
                      className={clsx(
                        'flex w-full items-center gap-2.5 rounded-lg px-2.5 py-1.5 text-left text-[13px] transition',
                        d.id === doc.domain ? 'font-semibold text-tt-navy' : 'text-tt-ink hover:bg-tt-mist/70',
                      )}
                    >
                      <span className="h-2 w-2 rounded-full" style={{ background: domainVisual(d.id).color }} />
                      <span className="flex-1">{d.name}</span>
                      {d.id === doc.domain && <Check size={14} className="text-tt-electric" />}
                    </button>
                  ))}
                  <div className="my-1 border-t border-tt-line" />
                  <button
                    onClick={() => {
                      setMenu(null)
                      run('suggest', async () => {
                        setSuggestion(await api.suggestDomain(doc.doc_id))
                      })
                    }}
                    className="flex w-full items-center gap-2.5 rounded-lg px-2.5 py-1.5 text-left text-[13px] font-medium text-tt-electric hover:bg-tt-electric/[0.06]"
                  >
                    <WandSparkles size={14} /> Suggest with AI
                  </button>
                </Menu>
              )}
            </div>

            {/* access */}
            <button
              onClick={() =>
                run('access', async () => {
                  const next = !doc.confidential
                  await api.setConfidential(doc.doc_id, next)
                  await onChanged()
                  return next ? 'Marked confidential: only super users and developers can see it' : 'Now visible to everyone with access to this domain'
                })
              }
              className={clsx(
                'inline-flex items-center gap-1.5 rounded-lg border px-2.5 py-1.5 text-[12.5px] font-semibold transition',
                doc.confidential ? 'border-[#f3c9b4] bg-[#fdf0ea] text-[#8a3510] hover:bg-[#fbe4d8]' : 'border-tt-line text-tt-slate hover:border-tt-periwinkle hover:text-tt-navy',
              )}
              title={doc.confidential ? 'Only super users and developers can see this. Click to make it visible to all users.' : 'Visible to all users with access to this domain. Click to mark confidential.'}
            >
              {busy === 'access' ? <LoaderCircle size={14} className="animate-spin" /> : doc.confidential ? <Lock size={14} /> : <LockOpen size={14} />}
              {doc.confidential ? 'Confidential' : 'Standard'}
            </button>

            {/* more */}
            <div className="relative">
              <button
                onClick={() => setMenu((m) => (m === 'more' ? null : 'more'))}
                className="flex h-[34px] w-[34px] items-center justify-center rounded-lg border border-tt-line text-tt-slate transition hover:border-tt-periwinkle hover:text-tt-navy"
                aria-label="More actions"
                title="More actions"
              >
                {busy === 'reprocess' || busy === 'delete' ? <LoaderCircle size={15} className="animate-spin" /> : <Ellipsis size={16} />}
              </button>
              {menu === 'more' && (
                <Menu onClose={() => setMenu(null)} width="w-56">
                  <button
                    onClick={() => {
                      setMenu(null)
                      run('reprocess', async () => {
                        const r = await api.reprocess(doc.doc_id)
                        await onChanged()
                        return `Re-processed in ${r.seconds}s`
                      })
                    }}
                    className="flex w-full items-center gap-2.5 rounded-lg px-2.5 py-2 text-left text-[13px] text-tt-ink hover:bg-tt-mist/70"
                  >
                    <RefreshCw size={14} className="text-tt-slate" /> Re-process document
                  </button>
                  <button
                    onClick={() => {
                      setMenu(null)
                      if (!confirm(`Remove "${cleanName(doc.file_name)}" from the knowledge base? The assistant will no longer use it.`)) return
                      run('delete', async () => {
                        await api.deleteDocument(doc.doc_id)
                        onDeleted()
                      })
                    }}
                    className="flex w-full items-center gap-2.5 rounded-lg px-2.5 py-2 text-left text-[13px] text-[#a8401a] hover:bg-[#fdf0ea]"
                  >
                    <Trash size={14} /> Remove document
                  </button>
                </Menu>
              )}
            </div>

            <span className="mx-1 h-5 w-px bg-tt-line" />
            <button
              onClick={onClose}
              className="flex h-[34px] w-[34px] items-center justify-center rounded-lg text-tt-slate transition hover:bg-tt-mist hover:text-tt-navy"
              aria-label="Close document"
              title="Close (back to library overview)"
            >
              <X size={17} />
            </button>
          </div>
        </div>

        <AnimatePresence>
          {suggestion && (
            <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: 'auto' }} exit={{ opacity: 0, height: 0 }} className="overflow-hidden">
              <div className="mt-3 flex flex-wrap items-center gap-3 rounded-xl border border-tt-periwinkle/30 bg-tt-electric/[0.03] px-4 py-2.5">
                <WandSparkles size={15} className="text-tt-electric" />
                <div className="min-w-0 flex-1 text-[13px]">
                  <span className="text-tt-slate">AI suggests </span>
                  <b className="text-tt-navy">{domainVisual(suggestion.domain).label}</b>
                  <span className="text-tt-slate"> · {Math.round(suggestion.confidence * 100)}% sure. {suggestion.reason}</span>
                </div>
                {suggestion.domain !== doc.domain ? (
                  <button onClick={() => setDomain(suggestion.domain)} className="rounded-lg bg-tt-electric px-3 py-1.5 text-[12.5px] font-semibold text-white hover:bg-tt-electric-600">
                    Move there
                  </button>
                ) : (
                  <span className="inline-flex items-center gap-1 text-[12.5px] font-semibold text-[#0b8f81]">
                    <CircleCheck size={15} /> Already there
                  </span>
                )}
                <button onClick={() => setSuggestion(null)} className="rounded-md p-1 text-tt-slate hover:bg-white" aria-label="Dismiss">
                  <X size={15} />
                </button>
              </div>
            </motion.div>
          )}
        </AnimatePresence>

        <div className="mt-3 flex gap-1 overflow-x-auto">
          {tabs
            .filter((t) => t.show)
            .map((t) => (
              <button
                key={t.id}
                onClick={() => setTab(t.id)}
                className={clsx(
                  'relative shrink-0 px-3 pt-1.5 pb-3 text-[13px] font-semibold transition',
                  tab === t.id ? 'text-tt-navy' : 'text-tt-slate hover:text-tt-navy',
                )}
              >
                {t.label}
                {t.count !== undefined && <span className="ml-1.5 font-normal text-tt-slate/70">{t.count}</span>}
                {tab === t.id && <span className="absolute inset-x-2 bottom-0 h-[2px] rounded-full bg-tt-electric" />}
              </button>
            ))}
        </div>
      </div>

      {/* body */}
      <div className="min-h-0 flex-1 bg-tt-canvas p-4 sm:p-5">
        {tab === 'overview' && (
          <OverviewTab
            doc={doc}
            onOpenSheet={(s) => {
              setSheet(s)
              setTab('preview')
            }}
          />
        )}
        {tab === 'preview' && (
          <SheetPreview preview={preview} loading={previewLoading} error={previewError} draft={draft} onDraft={setDraft} onSheet={setSheet} />
        )}
        {tab === 'records' && <RecordsTab preview={preview} onSheet={setSheet} />}
        {tab === 'images' && <ImagesTab doc={doc} onChanged={onChanged} />}
        {tab === 'chunks' && <ChunksTab doc={doc} />}
      </div>

      {/* pending corrections */}
      <AnimatePresence>
        {pending && (
          <motion.div
            initial={{ y: 40, opacity: 0 }}
            animate={{ y: 0, opacity: 1 }}
            exit={{ y: 40, opacity: 0 }}
            className="absolute inset-x-4 bottom-4 z-20 flex flex-wrap items-center gap-3 rounded-2xl bg-tt-navy px-5 py-3 text-white shadow-lift"
          >
            <span className="h-2 w-2 animate-pulse rounded-full bg-tt-amber" />
            <span className="flex-1 text-[13px]">
              <b>{pendingCount || 'Some'}</b> correction{pendingCount === 1 ? '' : 's'} not applied yet. Applying re-reads the file with your changes.
            </span>
            <button onClick={() => setDraft(doc.parse_options ?? {})} className="rounded-xl px-3 py-1.5 text-[12.5px] font-semibold text-white/80 hover:bg-white/10">
              Discard
            </button>
            <button
              onClick={apply}
              disabled={busy === 'apply'}
              className="inline-flex items-center gap-2 rounded-xl bg-white px-4 py-1.5 text-[12.5px] font-bold text-tt-electric disabled:opacity-60"
            >
              {busy === 'apply' && <LoaderCircle size={14} className="animate-spin" />}
              Apply changes
            </button>
          </motion.div>
        )}
      </AnimatePresence>

      <AnimatePresence>
        {toast && (
          <motion.div
            initial={{ y: -10, opacity: 0 }}
            animate={{ y: 0, opacity: 1 }}
            exit={{ y: -10, opacity: 0 }}
            className={clsx(
              'absolute top-3 left-1/2 z-30 flex max-w-[90%] -translate-x-1/2 items-center gap-2 rounded-xl px-4 py-2.5 text-[13px] font-medium shadow-lift',
              toast.kind === 'ok' ? 'bg-tt-navy text-white' : 'bg-[#8a3510] text-white',
            )}
          >
            {toast.kind === 'ok' ? <CircleCheck size={16} className="text-tt-teal" /> : <X size={16} />}
            {toast.text}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}

function Menu({ children, onClose, width = 'w-60' }: { children: ReactNode; onClose: () => void; width?: string }) {
  return (
    <>
      <div className="fixed inset-0 z-20" onClick={onClose} />
      <div className={clsx('absolute right-0 z-30 mt-1.5 rounded-xl border border-tt-line bg-white p-1 shadow-lift', width)}>{children}</div>
    </>
  )
}
