import clsx from 'clsx'
import { KeyRound, LoaderCircle, LogOut, X } from 'lucide-react'
import { AnimatePresence, motion } from 'motion/react'
import { useState } from 'react'
import { api } from '../lib/api'
import { auth, ROLE_LABEL, type AuthUser } from '../lib/auth'

const initials = (name: string) =>
  name.split(/[\s._-]+/).filter(Boolean).slice(0, 2).map((s) => s[0]?.toUpperCase()).join('') || '?'

export function AccountMenu({ user, rail }: { user: AuthUser; rail: boolean }) {
  const [open, setOpen] = useState(false)
  const [pwOpen, setPwOpen] = useState(false)
  return (
    <div className="relative m-3">
      <button
        onClick={() => setOpen((o) => !o)}
        className={clsx(
          'flex w-full items-center gap-3 rounded-2xl border border-white/10 bg-white/[0.05] p-2.5 text-left transition hover:bg-white/[0.09]',
          rail && 'lg:justify-center lg:border-0 lg:bg-transparent lg:p-0',
        )}
        title={`${user.display_name} · ${ROLE_LABEL[user.role]}`}
      >
        <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-white font-display text-[12.5px] font-bold text-tt-electric">
          {initials(user.display_name)}
        </span>
        <span className={clsx('min-w-0 flex-1', rail && 'lg:hidden')}>
          <span className="block truncate text-[13.5px] font-semibold text-white">{user.display_name}</span>
          <span className="block text-[11px] tracking-wide text-tt-teal-tint">{ROLE_LABEL[user.role].toUpperCase()}</span>
        </span>
      </button>
      <AnimatePresence>
        {open && (
          <>
            <div className="fixed inset-0 z-40" onClick={() => setOpen(false)} />
            <motion.div
              initial={{ opacity: 0, y: 6 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: 6 }}
              className="absolute bottom-full left-0 z-50 mb-2 w-60 rounded-2xl border border-tt-line bg-white p-1.5 text-tt-ink shadow-lift"
            >
              <div className="px-3 pt-2 pb-2.5">
                <div className="text-[13.5px] font-semibold text-tt-navy">{user.display_name}</div>
                <div className="text-[12px] text-tt-slate">@{user.username} · {ROLE_LABEL[user.role]}</div>
              </div>
              <button
                onClick={() => {
                  setOpen(false)
                  setPwOpen(true)
                }}
                className="flex w-full items-center gap-2.5 rounded-xl px-3 py-2 text-[13px] hover:bg-tt-mist"
              >
                <KeyRound size={15} className="text-tt-electric" /> Change password
              </button>
              <button onClick={() => auth.clear()} className="flex w-full items-center gap-2.5 rounded-xl px-3 py-2 text-[13px] text-[#8a3510] hover:bg-[#fdf0ea]">
                <LogOut size={15} /> Sign out
              </button>
            </motion.div>
          </>
        )}
      </AnimatePresence>
      <AnimatePresence>{pwOpen && <PasswordDialog onClose={() => setPwOpen(false)} />}</AnimatePresence>
    </div>
  )
}

function PasswordDialog({ onClose }: { onClose: () => void }) {
  const [current, setCurrent] = useState('')
  const [next, setNext] = useState('')
  const [confirm, setConfirm] = useState('')
  const [busy, setBusy] = useState(false)
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null)
  const input = 'w-full rounded-xl border border-tt-line px-3 py-2.5 text-[13.5px] text-tt-ink outline-none focus:border-tt-periwinkle focus:ring-4 focus:ring-tt-periwinkle/15'
  const invalid = next.length < 8 ? 'At least 8 characters' : next !== confirm ? 'Passwords do not match' : null

  const save = async () => {
    setBusy(true)
    setMsg(null)
    try {
      await api.changePassword(current, next)
      setMsg({ ok: true, text: 'Password changed. Other sessions were signed out.' })
      setTimeout(onClose, 1400)
    } catch (e) {
      setMsg({ ok: false, text: (e as Error).message })
    } finally {
      setBusy(false)
    }
  }

  return (
    <>
      <motion.div className="fixed inset-0 z-50 bg-tt-midnight/50" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} onClick={onClose} />
      <motion.div
        initial={{ opacity: 0, y: 16 }}
        animate={{ opacity: 1, y: 0 }}
        exit={{ opacity: 0, y: 16 }}
        className="fixed inset-x-3 top-[15vh] z-[60] mx-auto max-w-sm rounded-3xl bg-white p-6 text-tt-ink shadow-2xl"
      >
        <div className="flex items-center">
          <h3 className="font-display text-[17px] font-bold text-tt-navy">Change password</h3>
          <button onClick={onClose} className="ml-auto rounded-lg p-1.5 text-tt-slate hover:bg-tt-mist" aria-label="Close">
            <X size={17} />
          </button>
        </div>
        <div className="mt-4 space-y-3">
          <input type="password" autoComplete="current-password" value={current} onChange={(e) => setCurrent(e.target.value)} className={input} placeholder="Current password" />
          <input type="password" autoComplete="new-password" value={next} onChange={(e) => setNext(e.target.value)} className={input} placeholder="New password (min. 8 characters)" />
          <input type="password" autoComplete="new-password" value={confirm} onChange={(e) => setConfirm(e.target.value)} className={input} placeholder="Repeat new password" />
        </div>
        {next && invalid && <p className="mt-2 text-[12px] text-tt-ember">{invalid}</p>}
        {msg && <p className={clsx('mt-3 text-[12.5px]', msg.ok ? 'text-[#0b8f81]' : 'text-tt-ember')}>{msg.text}</p>}
        <button
          onClick={save}
          disabled={busy || !current || !!invalid}
          className="bg-tt-electric-gradient mt-5 flex w-full items-center justify-center gap-2 rounded-xl py-2.5 font-display text-[14px] font-semibold text-white disabled:opacity-50"
        >
          {busy && <LoaderCircle size={15} className="animate-spin" />}
          Update password
        </button>
      </motion.div>
    </>
  )
}
