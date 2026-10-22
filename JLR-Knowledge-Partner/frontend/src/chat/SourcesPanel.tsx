import clsx from 'clsx'
import { BookOpen, MapPin, X } from 'lucide-react'
import { motion } from 'motion/react'
import { useEffect, useRef, useState } from 'react'
import { AuthImage } from '../lib/AuthImage'
import { cleanName, FileBadge, locationLabel } from '../lib/format'
import type { Source } from '../lib/types'

type Props = {
  sources: Source[]
  highlight: number | null
  onClose?: () => void
}

function SourceCard({ s, highlighted }: { s: Source; highlighted: boolean }) {
  const ref = useRef<HTMLDivElement>(null)
  const [open, setOpen] = useState(false)
  useEffect(() => {
    if (highlighted) {
      ref.current?.scrollIntoView({ behavior: 'smooth', block: 'nearest' })
      setOpen(true)
    }
  }, [highlighted])
  const pct = Math.round(Math.min(1, Math.max(0, s.score)) * 100)
  return (
    <motion.div
      ref={ref}
      layout
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      className={clsx(
        'rounded-2xl border bg-white p-3.5 transition',
        highlighted ? 'border-tt-electric shadow-glow' : 'border-tt-line hover:border-tt-periwinkle/50 hover:shadow-card',
      )}
    >
      <div className="flex items-start gap-3">
        <div className="relative">
          <FileBadge type={s.file_type} />
          <span
            className={clsx(
              'absolute -top-1.5 -right-1.5 flex h-[18px] min-w-[18px] items-center justify-center rounded-full px-1 font-display text-[10px] font-bold ring-2 ring-white',
              s.cited ? 'bg-tt-electric text-white' : 'bg-tt-line text-tt-slate',
            )}
          >
            {s.n}
          </span>
        </div>
        <div className="min-w-0 flex-1">
          <div className="truncate text-[13.5px] font-semibold text-tt-navy" title={s.file_name}>
            {cleanName(s.file_name)}
          </div>
          <div className="mt-0.5 flex items-center gap-1 text-[12px] text-tt-slate">
            <MapPin size={12} className="shrink-0 text-tt-periwinkle" />
            <span className="truncate">{locationLabel(s.location) || 'Document'}</span>
          </div>
          {s.title && <div className="mt-1 truncate text-[12.5px] font-medium text-tt-ink/80">{s.title}</div>}
        </div>
      </div>
      <div className="mt-3 flex items-center gap-2">
        <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-tt-mist">
          <motion.div
            className="h-full rounded-full bg-gradient-to-r from-tt-electric to-tt-teal"
            initial={{ width: 0 }}
            animate={{ width: `${pct}%` }}
            transition={{ duration: 0.6, ease: 'easeOut' }}
          />
        </div>
        <span className="w-9 text-right font-display text-[11px] font-semibold text-tt-slate">{pct}%</span>
      </div>
      {s.image_id && (
        <button
          onClick={() => setOpen((o) => !o)}
          className="mt-2.5 block w-full overflow-hidden rounded-lg border border-tt-line bg-tt-mist/50"
          title={open ? 'Smaller' : 'Larger'}
        >
          <AuthImage id={s.image_id} thumb={!open} alt={`Picture from ${cleanName(s.file_name)}`} className={clsx('mx-auto w-full object-contain', open ? 'max-h-96' : 'h-36')} />
        </button>
      )}
      <button
        onClick={() => setOpen((o) => !o)}
        className="mt-2.5 block w-full rounded-lg bg-tt-mist/70 px-3 py-2 text-left text-[12.5px] leading-relaxed text-tt-ink/85 transition hover:bg-tt-mist"
        title={open ? 'Collapse' : 'Expand'}
      >
        <span className={clsx('block whitespace-pre-line [overflow-wrap:anywhere]', !open && 'line-clamp-3')}>{s.snippet}</span>
      </button>
    </motion.div>
  )
}

export function SourcesPanel({ sources, highlight, onClose }: Props) {
  const cited = sources.filter((s) => s.cited)
  const others = sources.filter((s) => !s.cited)
  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center gap-2 border-b border-tt-line px-5 py-4">
        <BookOpen size={17} className="text-tt-electric" />
        <h2 className="font-display text-[15px] font-bold text-tt-navy">Sources</h2>
        <span className="rounded-full bg-tt-mist px-2 py-0.5 text-[11.5px] font-semibold text-tt-slate">{sources.length}</span>
        {onClose && (
          <button onClick={onClose} className="ml-auto rounded-lg p-1.5 text-tt-slate transition hover:bg-tt-mist hover:text-tt-navy" aria-label="Close sources" title="Close sources">
            <X size={17} />
          </button>
        )}
      </div>
      <div className="scrollbar-thin flex-1 space-y-3 overflow-y-auto p-4">
        {sources.length === 0 ? (
          <div className="flex h-full flex-col items-center justify-center px-6 text-center">
            <div className="bg-grid flex h-16 w-16 items-center justify-center rounded-2xl border border-tt-line bg-white">
              <BookOpen size={24} className="text-tt-periwinkle" />
            </div>
            <p className="mt-4 font-display text-[14px] font-semibold text-tt-navy">Evidence appears here</p>
            <p className="mt-1 text-[12.5px] leading-relaxed text-tt-slate">
              Every answer is traced back to the exact sheet, row, page or slide it came from.
            </p>
          </div>
        ) : (
          <>
            {cited.length > 0 && <div className="px-1 font-display text-[11px] font-semibold tracking-[0.16em] text-tt-slate/70">CITED IN ANSWER</div>}
            {cited.map((s) => (
              <SourceCard key={`c-${s.n}`} s={s} highlighted={highlight === s.n} />
            ))}
            {others.length > 0 && (
              <div className="px-1 pt-2 font-display text-[11px] font-semibold tracking-[0.16em] text-tt-slate/70">ALSO RETRIEVED</div>
            )}
            {others.map((s) => (
              <SourceCard key={`o-${s.n}`} s={s} highlighted={highlight === s.n} />
            ))}
          </>
        )}
      </div>
    </div>
  )
}
