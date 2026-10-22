import { Check } from 'lucide-react'
import { motion } from 'motion/react'

const STEPS = [
  { id: 'plan', label: 'Understanding your question' },
  { id: 'retrieve', label: 'Searching the knowledge base' },
  { id: 'rewrite', label: 'Refining the search' },
  { id: 'generate', label: 'Writing the answer' },
]

/** Live progress while an answer is being prepared: the current step shimmers, finished steps tick off. */
export function Thinking({ steps }: { steps: { step: string; message?: string }[] }) {
  const seen = steps.map((s) => s.step)
  const current = steps[steps.length - 1]
  const order = STEPS.filter((s) => seen.includes(s.id))
  const label = current?.message && current.message !== '' ? current.message : 'Thinking'
  return (
    <div className="flex flex-col gap-1.5 py-1">
      {order.slice(0, -1).map((s) => (
        <motion.div key={s.id} initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="flex items-center gap-2 text-[13px] text-tt-slate/70">
          <Check size={13} className="text-tt-teal" strokeWidth={3} />
          {s.label}
        </motion.div>
      ))}
      <div className="flex items-center gap-2.5">
        <span className="relative flex h-2.5 w-2.5">
          <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-tt-periwinkle/50" />
          <span className="relative inline-flex h-2.5 w-2.5 rounded-full bg-tt-electric" />
        </span>
        <span className="shimmer-text text-[14px] font-medium">{label}…</span>
      </div>
    </div>
  )
}
