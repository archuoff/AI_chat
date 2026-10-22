import clsx from 'clsx'
import { LoaderCircle, Search } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { api } from '../lib/api'
import { locationLabel } from '../lib/format'
import type { ChunkInfo, DocumentInfo } from '../lib/types'

export function ChunksTab({ doc }: { doc: DocumentInfo }) {
  const [chunks, setChunks] = useState<ChunkInfo[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [q, setQ] = useState('')

  useEffect(() => {
    setChunks(null)
    api.chunks(doc.doc_id, 2000).then(setChunks).catch((e: Error) => setError(e.message))
  }, [doc.doc_id, doc.ingested_at])

  const shown = useMemo(() => {
    const t = q.trim().toLowerCase()
    return (chunks ?? []).filter((c) => !t || c.text.toLowerCase().includes(t) || c.context.toLowerCase().includes(t))
  }, [chunks, q])

  return (
    <div className="flex h-full min-h-0 flex-col gap-3">
      <div className="flex flex-wrap items-center gap-3">
        <p className="min-w-0 flex-1 text-[12.5px] text-tt-slate">
          The searchable pieces stored in Qdrant ({doc.chunks}). Each is embedded together with its context line ({doc.embedding_model ?? 'embedding model'}).
        </p>
        <div className="relative w-full sm:w-64">
          <Search size={15} className="absolute top-1/2 left-3 -translate-y-1/2 text-tt-slate/60" />
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Filter chunks…"
            className="w-full rounded-xl border border-tt-line bg-white py-2 pr-3 pl-9 text-[13px] outline-none focus:border-tt-periwinkle"
          />
        </div>
      </div>
      <div className="scrollbar-thin min-h-0 flex-1 space-y-3 overflow-y-auto">
        {!chunks && !error && (
          <div className="flex justify-center py-16">
            <LoaderCircle className="animate-spin text-tt-electric" />
          </div>
        )}
        {error && <p className="text-[13px] text-tt-ember">{error}</p>}
        {shown.map((c) => (
          <div key={c.id} className="rounded-2xl border border-tt-line bg-white p-4">
            <div className="flex flex-wrap items-center gap-2">
              <span className="rounded-md bg-tt-navy px-1.5 py-0.5 font-display text-[10.5px] font-bold text-white">#{c.chunk_index}</span>
              <span
                className={clsx(
                  'rounded-md px-2 py-0.5 text-[11px] font-semibold',
                  c.kind === 'record' ? 'bg-tt-green-tint text-tt-auto-dark' : 'bg-tt-periwinkle/15 text-tt-electric',
                )}
              >
                {c.kind === 'record' ? 'Table record' : 'Text'}
              </span>
              <span className="truncate text-[12px] text-tt-slate">{locationLabel(c.location)}</span>
            </div>
            <div className="mt-2 truncate font-display text-[11.5px] text-tt-slate/80" title={c.context}>
              {c.context}
            </div>
            {c.kind === 'record' && c.fields ? (
              <div className="mt-2.5 overflow-hidden rounded-xl border border-tt-line">
                <table className="w-full table-fixed text-[12.5px] [overflow-wrap:anywhere]">
                  <tbody>
                    {Object.entries(c.fields).map(([k, v]) => (
                      <tr key={k} className="border-t border-tt-line first:border-t-0">
                        <td className="w-[36%] bg-tt-mist/70 px-3 py-1.5 align-top font-semibold text-tt-navy">{k}</td>
                        <td className="px-3 py-1.5 align-top whitespace-pre-line text-tt-ink">{String(v)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <p className="mt-2.5 text-[13px] leading-relaxed whitespace-pre-line text-tt-ink/90 [overflow-wrap:anywhere]">{c.text}</p>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}
