import clsx from 'clsx'
import { Check, Copy, Info, Layers, Pencil, TriangleAlert, Zap } from 'lucide-react'
import { motion } from 'motion/react'
import { useEffect, useRef, useState } from 'react'
import { JlrLogo } from '../components/Brand'
import type { UIMessage } from '../lib/types'
import { AnswerMarkdown } from './Markdown'
import { Thinking } from './StatusSteps'

const INTENT_LABEL: Record<string, string> = {
  lookup: 'Fact lookup',
  comparison: 'Comparison',
  list: 'List',
  explanation: 'Explanation',
  exact_id: 'Exact ID',
  chitchat: 'Conversation',
}

const STEP_LABEL: Record<string, string> = {
  plan: 'Understand question',
  'retrieve.embed': 'Embed question',
  'retrieve.search': 'Search Qdrant',
  'retrieve.rerank': 'Rank evidence',
  'retrieve.judge': 'Check relevance',
  rewrite: 'Rephrase search',
  generate: 'Write answer',
}

function timingTitle(t?: Record<string, number>) {
  if (!t) return 'Response time'
  return Object.entries(STEP_LABEL)
    .filter(([k]) => t[k] !== undefined)
    .map(([k, label]) => `${label}: ${(t[k] / 1000).toFixed(1)} s`)
    .join('\n')
}

type Props = {
  msg: UIMessage
  active: boolean
  onCite: (n: number) => void
  onShowSources: () => void
  /** edit and send: the later conversation is dropped and the new text is asked instead (undefined = not offered) */
  onEdit?: (text: string) => void
}

export function MessageView({ msg, active, onCite, onShowSources, onEdit }: Props) {
  const [copied, setCopied] = useState(false)
  const [zoom, setZoom] = useState<string | null>(null)
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState(msg.content)
  const box = useRef<HTMLTextAreaElement>(null)

  useEffect(() => {
    if (!editing) return
    const el = box.current
    if (!el) return
    el.focus()
    el.setSelectionRange(el.value.length, el.value.length)
  }, [editing])
  useEffect(() => {
    const el = box.current
    if (!el) return
    el.style.height = '0px'
    el.style.height = `${Math.min(el.scrollHeight, 240)}px`
  }, [draft, editing])

  if (msg.role === 'user') {
    return (
      <motion.div initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.2 }} className="flex flex-col items-end gap-2">
        {msg.images && msg.images.length > 0 && (
          <div className="flex max-w-[80%] flex-wrap justify-end gap-2">
            {msg.images.map((src, i) => (
              <button
                key={i}
                onClick={() => setZoom(src)}
                className="overflow-hidden rounded-2xl border border-tt-line bg-white transition hover:shadow-card"
                title="Open image"
              >
                <img src={src} alt={`Attached image ${i + 1}`} className="h-28 w-auto max-w-[200px] object-cover" />
              </button>
            ))}
          </div>
        )}
        {msg.content && !editing && (
          <div className="group/q flex max-w-[80%] items-start gap-1.5">
            {onEdit && (
              <button
                onClick={() => {
                  setDraft(msg.content)
                  setEditing(true)
                }}
                className="mt-1.5 rounded-lg p-1.5 text-tt-slate opacity-0 transition group-hover/q:opacity-100 hover:bg-tt-mist hover:text-tt-navy focus:opacity-100"
                title="Edit and send again"
                aria-label="Edit this question"
              >
                <Pencil size={14} />
              </button>
            )}
            <div className="rounded-3xl rounded-br-lg bg-[#eaedfd] px-4 py-2.5 text-[15px] leading-relaxed whitespace-pre-wrap text-tt-navy">{msg.content}</div>
          </div>
        )}
        {editing && (
          <div className="w-full max-w-[80%] rounded-3xl border border-tt-periwinkle/60 bg-white p-3 shadow-card">
            <textarea
              ref={box}
              value={draft}
              rows={1}
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !e.shiftKey && draft.trim()) {
                  e.preventDefault()
                  setEditing(false)
                  onEdit?.(draft.trim())
                }
                if (e.key === 'Escape') setEditing(false)
              }}
              className="block max-h-60 w-full resize-none bg-transparent px-1 text-[15px] leading-relaxed text-tt-ink outline-none"
              aria-label="Edit your question"
            />
            {msg.images && msg.images.length > 0 && (
              <p className="mt-1 px-1 text-[12px] text-tt-slate">Attached images are not kept when you edit: add them again if they matter.</p>
            )}
            <p className="mt-1 px-1 text-[12px] text-tt-slate">Sending again removes the answers that followed this question.</p>
            <div className="mt-2 flex justify-end gap-2">
              <button onClick={() => setEditing(false)} className="rounded-xl px-3.5 py-1.5 text-[13px] font-semibold text-tt-slate hover:bg-tt-mist">
                Cancel
              </button>
              <button
                onClick={() => {
                  setEditing(false)
                  onEdit?.(draft.trim())
                }}
                disabled={!draft.trim()}
                className="rounded-xl bg-tt-electric px-4 py-1.5 text-[13px] font-semibold text-white hover:bg-tt-electric-600 disabled:opacity-40"
              >
                Send
              </button>
            </div>
          </div>
        )}
        {zoom && (
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-tt-midnight/80 p-6" onClick={() => setZoom(null)}>
            <img src={zoom} alt="Attached image" className="max-h-full max-w-full rounded-2xl bg-white shadow-2xl" />
          </div>
        )}
      </motion.div>
    )
  }

  const sources = msg.sources ?? []
  const cited = sources.filter((s) => s.cited).length
  const azure = msg.mode === 'azure-openai'
  const done = !msg.streaming && msg.intent !== 'chitchat'
  const meta = [
    msg.intent && msg.intent !== 'chitchat' ? INTENT_LABEL[msg.intent] ?? msg.intent : null,
    done && msg.mode ? (azure ? 'Azure OpenAI' : 'Extracted from sources') : null,
  ].filter(Boolean)

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(msg.content)
      setCopied(true)
      setTimeout(() => setCopied(false), 1400)
    } catch {
      /* clipboard blocked */
    }
  }

  return (
    <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.25 }} className="group">
      <div className="flex items-center gap-2.5">
        <span className="bg-tt-electric-gradient flex h-7 w-7 shrink-0 items-center justify-center rounded-lg text-white shadow-[0_4px_12px_-4px_rgba(0,0,179,0.6)]">
          <JlrLogo className="w-[60%]" />
        </span>
        <span className="font-display text-[14px] font-bold text-tt-navy">Knowledge Partner</span>
        {meta.length > 0 && <span className="truncate text-[12.5px] text-tt-slate/70">{meta.join(' · ')}</span>}
      </div>

      <div className={clsx('mt-2 pl-[38px]', active && 'relative')}>
        {active && <span className="absolute top-1 bottom-1 left-[13px] w-[2px] rounded-full bg-tt-periwinkle/40" />}
        {msg.streaming && !msg.content && <Thinking steps={msg.steps ?? []} />}
        {msg.content && <AnswerMarkdown text={msg.content} onCite={onCite} streaming={msg.streaming} />}

        {msg.error && (
          <div className="mt-3 flex items-start gap-2 rounded-xl bg-[#fdf0ea] px-3.5 py-2.5 text-[13.5px] text-[#8a3510]">
            <TriangleAlert size={16} className="mt-0.5 shrink-0" />
            {msg.error}
          </div>
        )}
        {msg.notices?.map((n, i) => (
          <div key={i} className="mt-3 flex items-start gap-2 rounded-xl bg-tt-amber-tint px-3.5 py-2.5 text-[13px] text-[#7a4705]">
            <Info size={15} className="mt-0.5 shrink-0" />
            {n}
          </div>
        ))}

        {done && msg.content && (
          <div className="mt-3 flex flex-wrap items-center gap-1 text-[12.5px] text-tt-slate opacity-80 transition group-hover:opacity-100">
            <button onClick={copy} className="inline-flex items-center gap-1.5 rounded-lg px-2 py-1.5 transition hover:bg-tt-mist hover:text-tt-navy" title="Copy answer">
              {copied ? <Check size={14} className="text-tt-teal" /> : <Copy size={14} />}
              {copied ? 'Copied' : 'Copy'}
            </button>
            {sources.length > 0 && (
              <button
                onClick={onShowSources}
                className={clsx(
                  'inline-flex items-center gap-1.5 rounded-lg px-2 py-1.5 transition hover:bg-tt-mist hover:text-tt-navy',
                  active && 'bg-tt-electric/[0.06] text-tt-electric',
                )}
              >
                <Layers size={14} />
                {cited ? `${cited} cited` : `${sources.length} sources`}
              </button>
            )}
            {msg.elapsedMs !== undefined && (
              <span className="inline-flex items-center gap-1 px-2 py-1.5 tabular-nums" title={timingTitle(msg.timings)}>
                <Zap size={13} className="text-tt-periwinkle" />
                {(msg.elapsedMs / 1000).toFixed(1)}s
              </span>
            )}
          </div>
        )}
      </div>
    </motion.div>
  )
}
