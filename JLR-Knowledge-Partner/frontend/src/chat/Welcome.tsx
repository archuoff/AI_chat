import { ArrowRight, FileSpreadsheet, Presentation, ShieldCheck, Table2 } from 'lucide-react'
import { motion } from 'motion/react'
import { AppMark } from '../components/Brand'
import { api } from '../lib/api'

// one pool across domains; only those in the user's allowed domains are shown
const SUGGESTIONS = [
  { q: 'Compare CCB weight across vehicles', tag: 'Benchmarking', domain: 'benchmarking', Icon: Table2 },
  { q: 'What causes decoupling ring failures?', tag: 'FMEA', domain: 'adas', Icon: ShieldCheck },
  { q: 'What is the minimum bond flange for the carbon fiber bonnet?', tag: 'Design guideline', domain: 'eds', Icon: Presentation },
  { q: 'What material is the BMW X5 cross car beam made of?', tag: 'Benchmarking', domain: 'benchmarking', Icon: FileSpreadsheet },
  { q: 'List the ultrasonic sensors and their package zones', tag: 'ADAS design rule', domain: 'adas', Icon: Table2 },
  { q: 'What is the minimum detachment force for the sensor holder?', tag: 'ADAS design rule', domain: 'adas', Icon: ShieldCheck },
  { q: 'What is the frunk volume of the BMW i3?', tag: 'Design guideline', domain: 'eds', Icon: Presentation },
  { q: 'How do I raise a PR AIMS?', tag: 'Lead engineering', domain: 'lead-engineering', Icon: FileSpreadsheet },
]

type Props = { onAsk: (q: string) => void; domains: string[] }

export function Welcome({ onAsk, domains }: Props) {
  const allowed = new Set(domains)
  const picks = SUGGESTIONS.filter((s) => allowed.has(s.domain))
  // a balanced first four: one per domain first, then the rest
  const seen = new Set<string>()
  const ordered = [...picks.filter((s) => !seen.has(s.domain) && seen.add(s.domain)), ...picks].filter((s, i, a) => a.indexOf(s) === i)
  const shown = ordered.slice(0, 4)
  return (
    <div className="mx-auto flex w-full max-w-3xl flex-col items-center px-4 pt-[8vh] pb-8 text-center sm:px-6">
      <motion.div initial={{ opacity: 0, scale: 0.9 }} animate={{ opacity: 1, scale: 1 }} transition={{ duration: 0.5 }} className="relative">
        <div className="absolute inset-0 -z-10 scale-[2.2] rounded-full bg-tt-periwinkle/25 blur-3xl" />
        <AppMark size={68} />
      </motion.div>
      <motion.h2
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.08 }}
        className="mt-7 font-display text-[34px] leading-[1.15] font-extrabold text-tt-navy sm:text-[42px]"
      >
        How can I support your <span className="text-tt-gradient">engineering work today?</span>
      </motion.h2>
      <motion.p
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.16 }}
        className="mt-4 max-w-xl text-[15.5px] leading-relaxed text-tt-slate"
      >
        Get reliable, source-referenced answers from your organisation's engineering standards, design guidelines and
        benchmarking data.
      </motion.p>
      <div className="mt-10 grid w-full gap-3 sm:grid-cols-2">
        {shown.map(({ q, tag, Icon }, i) => (
          <motion.button
            key={q}
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.22 + i * 0.06 }}
            onClick={() => onAsk(q)}
            onMouseEnter={api.warmup}
            className="group relative overflow-hidden rounded-2xl border border-tt-line bg-white p-4 text-left shadow-card transition hover:-translate-y-0.5 hover:border-tt-periwinkle/60 hover:shadow-lift"
          >
            <div className="flex items-center gap-2 text-[11.5px] font-semibold tracking-wide text-tt-electric">
              <span className="flex h-6 w-6 items-center justify-center rounded-lg bg-tt-electric/[0.07]">
                <Icon size={13} />
              </span>
              {tag.toUpperCase()}
            </div>
            <div className="mt-2.5 pr-6 text-[14.5px] leading-snug font-medium text-tt-ink">{q}</div>
            <ArrowRight
              size={16}
              className="absolute right-4 bottom-4 text-tt-periwinkle opacity-0 transition group-hover:translate-x-0.5 group-hover:opacity-100"
            />
          </motion.button>
        ))}
      </div>
    </div>
  )
}
