import { ArrowRight, Eye, EyeOff, LoaderCircle, LockKeyhole, ShieldCheck, UserRound } from 'lucide-react'
import { motion } from 'motion/react'
import { useState } from 'react'
import { api } from '../lib/api'
import { JlrLogo } from './Brand'

const POINTS = [
  'Answers grounded in benchmarking, FMEA and design-guideline documents',
  'Every fact traced to the exact sheet, row, page or slide',
  'Access controlled per role and engineering domain',
]

export function LoginView() {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [show, setShow] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!username.trim() || !password) return
    setBusy(true)
    setError(null)
    try {
      await api.login(username.trim(), password)
    } catch (err) {
      setError((err as Error).message)
    } finally {
      setBusy(false)
    }
  }

  const field =
    'w-full rounded-xl border border-tt-line bg-white py-3 pr-3 pl-10 text-[14.5px] text-tt-ink outline-none transition focus:border-tt-periwinkle focus:ring-4 focus:ring-tt-periwinkle/15'

  return (
    <div className="flex min-h-full flex-col lg:flex-row">
      {/* brand panel */}
      <div className="bg-tt-sidebar relative flex flex-col justify-between overflow-hidden px-8 py-10 text-white lg:w-[46%] lg:px-14 lg:py-14">
        <div className="bg-grid pointer-events-none absolute inset-0 opacity-[0.07] invert" />
        <div className="relative flex items-center gap-4">
          <JlrLogo className="h-11 w-auto text-white" />
          <div className="h-10 w-px bg-white/25" />
          <div className="leading-tight">
            <div className="font-display text-[20px] font-bold">Knowledge Partner</div>
            <div className="mt-0.5 font-display text-[11px] font-bold tracking-[0.28em] text-tt-teal-tint">TATA TECHNOLOGIES</div>
          </div>
        </div>
        <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.5 }} className="relative mt-12 lg:mt-0">
          <h1 className="max-w-md font-display text-[34px] leading-[1.15] font-extrabold lg:text-[42px]">
            Trusted engineering knowledge, <span className="text-tt-teal-tint">at your fingertips.</span>
          </h1>
          <ul className="mt-8 hidden space-y-3.5 sm:block">
            {POINTS.map((p) => (
              <li key={p} className="flex items-start gap-3 text-[14.5px] text-white/80">
                <ShieldCheck size={18} className="mt-0.5 shrink-0 text-tt-teal" />
                {p}
              </li>
            ))}
          </ul>
        </motion.div>
        <p className="relative mt-10 hidden text-[12px] text-white/40 lg:block">For authorised JLR and Tata Technologies users only.</p>
      </div>

      {/* sign-in form */}
      <div className="bg-tt-canvas flex flex-1 items-center justify-center px-6 py-12">
        <motion.form
          onSubmit={submit}
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.45, delay: 0.1 }}
          className="w-full max-w-[400px]"
        >
          <h2 className="font-display text-[26px] font-bold text-tt-navy">Sign in</h2>
          <p className="mt-1.5 text-[14px] text-tt-slate">Use the account your administrator created for you.</p>

          <label className="mt-8 block">
            <span className="mb-1.5 block text-[12.5px] font-semibold text-tt-slate">Username</span>
            <span className="relative block">
              <UserRound size={17} className="absolute top-1/2 left-3.5 -translate-y-1/2 text-tt-slate/60" />
              <input autoFocus autoComplete="username" value={username} onChange={(e) => setUsername(e.target.value)} className={field} />
            </span>
          </label>
          <label className="mt-4 block">
            <span className="mb-1.5 block text-[12.5px] font-semibold text-tt-slate">Password</span>
            <span className="relative block">
              <LockKeyhole size={17} className="absolute top-1/2 left-3.5 -translate-y-1/2 text-tt-slate/60" />
              <input
                type={show ? 'text' : 'password'}
                autoComplete="current-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className={`${field} pr-11`}
                placeholder="••••••••"
              />
              <button
                type="button"
                onClick={() => setShow((s) => !s)}
                className="absolute top-1/2 right-2 -translate-y-1/2 rounded-lg p-1.5 text-tt-slate/70 hover:bg-tt-mist"
                aria-label={show ? 'Hide password' : 'Show password'}
              >
                {show ? <EyeOff size={16} /> : <Eye size={16} />}
              </button>
            </span>
          </label>

          {error && <div className="mt-4 rounded-xl border border-tt-ember/30 bg-[#fdf0ea] px-3.5 py-2.5 text-[13px] text-[#8a3510]">{error}</div>}

          <button
            type="submit"
            disabled={busy || !username.trim() || !password}
            className="bg-tt-electric-gradient mt-6 flex w-full items-center justify-center gap-2 rounded-xl py-3 font-display text-[15px] font-semibold text-white shadow-[0_12px_28px_-12px_rgba(0,0,179,0.9)] transition hover:-translate-y-px disabled:translate-y-0 disabled:opacity-50"
          >
            {busy ? <LoaderCircle size={18} className="animate-spin" /> : <ArrowRight size={18} />}
            {busy ? 'Signing in…' : 'Sign in'}
          </button>
          <p className="mt-6 text-center text-[12px] text-tt-slate/70">Forgot your password? Ask a developer to reset it.</p>
        </motion.form>
      </div>
    </div>
  )
}
