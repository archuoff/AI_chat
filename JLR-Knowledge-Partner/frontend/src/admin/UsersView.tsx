import clsx from 'clsx'
import { Activity, Coins, KeyRound, LoaderCircle, MessagesSquare, Pencil, SearchX, Trash, UserPlus, Users, X } from 'lucide-react'
import { AnimatePresence, motion } from 'motion/react'
import { useCallback, useEffect, useMemo, useState } from 'react'
import { api } from '../lib/api'
import { auth, ROLE_LABEL, type Role } from '../lib/auth'
import { DomainChip, DomainIcon, domainVisual } from '../lib/domains'
import { timeAgo } from '../lib/format'
import type { Domain, ManagedUser, UsageSummary } from '../lib/types'

const ROLE_INFO: Record<Role, { text: string; cls: string }> = {
  user: { text: 'Chat only. Selected domains; never sees confidential documents.', cls: 'bg-tt-mist text-tt-slate' },
  superuser: { text: 'Chat across every domain, including confidential documents.', cls: 'bg-tt-periwinkle/15 text-tt-electric' },
  developer: { text: 'Everything: Manage knowledge, ingestion, Users & usage.', cls: 'bg-tt-navy text-white' },
}

const fmt = (n: number) => (n >= 1_000_000 ? `${(n / 1_000_000).toFixed(1)}M` : n >= 1000 ? `${(n / 1000).toFixed(1)}k` : String(n))

function Tile({ label, value, sub, Icon, accent }: { label: string; value: string; sub?: string; Icon: typeof Users; accent: string }) {
  return (
    <div className="rounded-2xl border border-tt-line bg-white p-4">
      <div className="flex items-center gap-2.5">
        <span className={clsx('flex h-9 w-9 items-center justify-center rounded-xl text-white', accent)}>
          <Icon size={17} />
        </span>
        <span className="text-[12.5px] font-semibold text-tt-slate">{label}</span>
      </div>
      <div className="mt-3 font-display text-[26px] leading-none font-extrabold text-tt-navy">{value}</div>
      {sub && <div className="mt-1.5 text-[12px] text-tt-slate">{sub}</div>}
    </div>
  )
}

function initials(name: string) {
  return name.split(/[\s._-]+/).filter(Boolean).slice(0, 2).map((s) => s[0]?.toUpperCase()).join('') || '?'
}

export function UsersView() {
  const [users, setUsers] = useState<ManagedUser[] | null>(null)
  const [usage, setUsage] = useState<UsageSummary | null>(null)
  const [domains, setDomains] = useState<Domain[]>([])
  const [days, setDays] = useState(30)
  const [editing, setEditing] = useState<ManagedUser | 'new' | null>(null)
  const [error, setError] = useState<string | null>(null)
  const me = auth.user()

  const load = useCallback(() => {
    api.users().then(setUsers).catch((e: Error) => setError(e.message))
    api.usage(days).then(setUsage).catch(() => {})
  }, [days])
  useEffect(load, [load])
  useEffect(() => {
    api.domains().then((d) => setDomains(d.filter((x) => x.id !== 'unassigned'))).catch(() => {})
  }, [])

  const usageById = useMemo(() => new Map((usage?.per_user ?? []).map((u) => [u.user_id, u])), [usage])
  const t = usage?.totals

  const remove = async (u: ManagedUser) => {
    if (!confirm(`Delete the account "${u.username}"? Their usage history is deleted too.`)) return
    try {
      await api.deleteUser(u.id)
      load()
    } catch (e) {
      setError((e as Error).message)
    }
  }

  return (
    <div className="bg-tt-canvas scrollbar-thin flex-1 overflow-y-auto">
      <div className="mx-auto max-w-6xl space-y-5 px-4 py-6 sm:px-6">
        <div className="flex flex-wrap items-center gap-3">
          <h2 className="font-display text-[18px] font-bold text-tt-navy">Usage</h2>
          <div className="flex rounded-xl bg-white p-1 ring-1 ring-tt-line">
            {[7, 30, 90].map((d) => (
              <button
                key={d}
                onClick={() => setDays(d)}
                className={clsx('rounded-lg px-3 py-1 text-[12.5px] font-semibold transition', days === d ? 'bg-tt-navy text-white' : 'text-tt-slate hover:text-tt-navy')}
              >
                {d} days
              </button>
            ))}
          </div>
        </div>
        <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
          <Tile label="Questions asked" value={t ? fmt(t.questions) : '–'} sub={`last ${days} days`} Icon={MessagesSquare} accent="bg-tt-electric" />
          <Tile
            label="LLM tokens"
            value={t ? fmt(t.input_tokens + t.output_tokens) : '–'}
            sub={t ? `${fmt(t.input_tokens)} in · ${fmt(t.output_tokens)} out` : undefined}
            Icon={Coins}
            accent="bg-tt-periwinkle"
          />
          <Tile label="Active users" value={t ? `${t.active_users}` : '–'} sub={t ? `of ${t.users} accounts` : undefined} Icon={Activity} accent="bg-tt-teal" />
          <Tile
            label="Not found answers"
            value={t ? `${t.not_found}` : '–'}
            sub={t && t.questions ? `${Math.round((100 * t.not_found) / t.questions)}% of questions: content gaps` : undefined}
            Icon={SearchX}
            accent="bg-tt-amber"
          />
        </div>

        <section className="rounded-3xl border border-tt-line bg-white">
          <div className="flex flex-wrap items-center gap-3 border-b border-tt-line px-5 py-4">
            <Users size={18} className="text-tt-electric" />
            <h2 className="font-display text-[17px] font-bold text-tt-navy">People</h2>
            <span className="rounded-full bg-tt-mist px-2 py-0.5 text-[11.5px] font-semibold text-tt-slate">{users?.length ?? 0}</span>
            <button
              onClick={() => setEditing('new')}
              className="bg-tt-electric-gradient ml-auto inline-flex items-center gap-2 rounded-xl px-4 py-2 font-display text-[13.5px] font-semibold text-white shadow-[0_10px_24px_-12px_rgba(0,0,179,0.9)] transition hover:-translate-y-px"
            >
              <UserPlus size={16} /> Create account
            </button>
          </div>
          {error && <div className="mx-5 mt-4 rounded-xl border border-tt-ember/30 bg-[#fdf0ea] px-3.5 py-2.5 text-[13px] text-[#8a3510]">{error}</div>}
          {!users ? (
            <div className="flex justify-center py-14">
              <LoaderCircle className="animate-spin text-tt-electric" />
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full min-w-[860px] text-left">
                <thead>
                  <tr className="text-[11.5px] font-semibold tracking-wide text-tt-slate/80 uppercase">
                    <th className="px-5 py-3">Person</th>
                    <th className="px-3 py-3">Role</th>
                    <th className="px-3 py-3">Domain access</th>
                    <th className="px-3 py-3">Questions</th>
                    <th className="px-3 py-3">Tokens</th>
                    <th className="px-3 py-3">Last active</th>
                    <th className="px-5 py-3" />
                  </tr>
                </thead>
                <tbody>
                  {users.map((u) => {
                    const s = usageById.get(u.id)
                    return (
                      <tr key={u.id} className={clsx('group border-t border-tt-line transition hover:bg-tt-mist/50', !u.is_active && 'opacity-55')}>
                        <td className="px-5 py-3">
                          <div className="flex items-center gap-3">
                            <span className="bg-tt-electric-gradient flex h-9 w-9 shrink-0 items-center justify-center rounded-full font-display text-[12.5px] font-bold text-white">
                              {initials(u.display_name)}
                            </span>
                            <div className="min-w-0">
                              <div className="truncate text-[13.5px] font-semibold text-tt-navy">
                                {u.display_name}
                                {u.id === me?.id && <span className="ml-1.5 text-[11px] font-medium text-tt-slate">(you)</span>}
                              </div>
                              <div className="text-[12px] text-tt-slate">
                                @{u.username}
                                {!u.is_active && <span className="ml-1.5 font-semibold text-tt-ember">· disabled</span>}
                              </div>
                            </div>
                          </div>
                        </td>
                        <td className="px-3 py-3">
                          <span className={clsx('rounded-md px-2 py-1 text-[11.5px] font-bold', ROLE_INFO[u.role].cls)}>{ROLE_LABEL[u.role]}</span>
                        </td>
                        <td className="px-3 py-3">
                          {u.role !== 'user' ? (
                            <span className="text-[12px] font-medium text-tt-slate">All domains + confidential</span>
                          ) : u.domains.length === 0 ? (
                            <span className="text-[12px] font-medium text-tt-slate">All domains</span>
                          ) : (
                            <div className="flex max-w-[260px] flex-wrap gap-1">
                              {u.domains.map((d) => (
                                <DomainChip key={d} id={d} />
                              ))}
                            </div>
                          )}
                        </td>
                        <td className="px-3 py-3 font-display text-[14px] font-bold text-tt-navy">{s?.questions ?? 0}</td>
                        <td className="px-3 py-3 text-[12.5px] text-tt-ink">
                          {s ? (
                            <>
                              <span className="font-display text-[14px] font-bold text-tt-navy">{fmt(s.input_tokens + s.output_tokens)}</span>
                              <span className="ml-1 text-tt-slate">({fmt(s.input_tokens)} / {fmt(s.output_tokens)})</span>
                            </>
                          ) : (
                            '0'
                          )}
                        </td>
                        <td className="px-3 py-3 text-[12.5px] whitespace-nowrap text-tt-slate">
                          {s?.last_active ? timeAgo(s.last_active) : u.last_login_at ? `signed in ${timeAgo(u.last_login_at)}` : 'never'}
                        </td>
                        <td className="px-5 py-3">
                          <div className="flex justify-end gap-1">
                            <button onClick={() => setEditing(u)} className="rounded-lg p-2 text-tt-slate transition hover:bg-tt-electric hover:text-white" title="Edit">
                              <Pencil size={15} />
                            </button>
                            {u.id !== me?.id && (
                              <button onClick={() => remove(u)} className="rounded-lg p-2 text-tt-slate transition hover:bg-tt-ember hover:text-white" title="Delete">
                                <Trash size={15} />
                              </button>
                            )}
                          </div>
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          )}
        </section>
      </div>

      <AnimatePresence>
        {editing && (
          <UserDialog
            user={editing === 'new' ? null : editing}
            domains={domains}
            isSelf={editing !== 'new' && editing.id === me?.id}
            onClose={() => setEditing(null)}
            onSaved={() => {
              setEditing(null)
              load()
            }}
          />
        )}
      </AnimatePresence>
    </div>
  )
}

function randomPassword() {
  const chars = 'ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789'
  const a = new Uint32Array(14)
  crypto.getRandomValues(a)
  return Array.from(a, (n) => chars[n % chars.length]).join('')
}

type DialogProps = { user: ManagedUser | null; domains: Domain[]; isSelf: boolean; onClose: () => void; onSaved: () => void }

function UserDialog({ user, domains, isSelf, onClose, onSaved }: DialogProps) {
  const [username, setUsername] = useState(user?.username ?? '')
  const [displayName, setDisplayName] = useState(user?.display_name ?? '')
  const [role, setRole] = useState<Role>(user?.role ?? 'user')
  const [allowed, setAllowed] = useState<string[]>(user?.domains ?? [])
  const [active, setActive] = useState(user?.is_active ?? true)
  const [password, setPassword] = useState(user ? '' : randomPassword())
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const input =
    'w-full rounded-xl border border-tt-line bg-white px-3 py-2.5 text-[13.5px] outline-none transition focus:border-tt-periwinkle focus:ring-4 focus:ring-tt-periwinkle/15'

  const save = async () => {
    setBusy(true)
    setError(null)
    try {
      if (user) {
        await api.updateUser(user.id, {
          display_name: displayName,
          role,
          domains: role === 'user' ? allowed : [],
          is_active: active,
          ...(password ? { password } : {}),
        })
      } else {
        await api.createUser({ username, display_name: displayName, password, role, domains: role === 'user' ? allowed : [] })
      }
      onSaved()
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <>
      <motion.div className="fixed inset-0 z-40 bg-tt-midnight/50" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} onClick={onClose} />
      <motion.div
        initial={{ opacity: 0, y: 20, scale: 0.98 }}
        animate={{ opacity: 1, y: 0, scale: 1 }}
        exit={{ opacity: 0, y: 20, scale: 0.98 }}
        className="fixed inset-x-3 top-[5vh] z-50 mx-auto max-h-[90vh] max-w-2xl overflow-y-auto rounded-3xl bg-white p-6 shadow-2xl"
      >
        <div className="flex items-center gap-2">
          <h3 className="font-display text-[18px] font-bold text-tt-navy">{user ? `Edit ${user.display_name}` : 'Create account'}</h3>
          <button onClick={onClose} className="ml-auto rounded-lg p-1.5 text-tt-slate hover:bg-tt-mist" aria-label="Close">
            <X size={18} />
          </button>
        </div>

        <div className="mt-5 grid gap-3 sm:grid-cols-2">
          <label className="block">
            <span className="mb-1 block text-[12px] font-semibold text-tt-slate">Username</span>
            <input value={username} onChange={(e) => setUsername(e.target.value)} disabled={!!user} className={clsx(input, user && 'bg-tt-mist text-tt-slate')} />
          </label>
          <label className="block">
            <span className="mb-1 block text-[12px] font-semibold text-tt-slate">Display name</span>
            <input value={displayName} onChange={(e) => setDisplayName(e.target.value)} className={input} />
          </label>
        </div>

        <div className="mt-4">
          <span className="mb-1.5 block text-[12px] font-semibold text-tt-slate">Role</span>
          <div className="grid gap-2 sm:grid-cols-3">
            {(Object.keys(ROLE_INFO) as Role[]).map((r) => (
              <button
                key={r}
                type="button"
                disabled={isSelf && r !== 'developer'}
                onClick={() => setRole(r)}
                className={clsx(
                  'rounded-xl border p-3 text-left transition disabled:cursor-not-allowed disabled:opacity-40',
                  role === r ? 'border-tt-electric bg-tt-electric/[0.04] shadow-glow' : 'border-tt-line hover:border-tt-periwinkle',
                )}
              >
                <div className="font-display text-[13.5px] font-bold text-tt-navy">{ROLE_LABEL[r]}</div>
                <div className="mt-1 text-[11.5px] leading-snug text-tt-slate">{ROLE_INFO[r].text}</div>
              </button>
            ))}
          </div>
        </div>

        {role === 'user' && (
          <div className="mt-4">
            <span className="mb-1.5 block text-[12px] font-semibold text-tt-slate">
              Domain access <span className="font-normal text-tt-slate/70">— none selected = all domains (confidential documents stay hidden)</span>
            </span>
            <div className="flex flex-wrap gap-2">
              {domains.map((d) => {
                const on = allowed.includes(d.id)
                const v = domainVisual(d.id)
                return (
                  <button
                    key={d.id}
                    type="button"
                    onClick={() => setAllowed((cur) => (on ? cur.filter((x) => x !== d.id) : [...cur, d.id]))}
                    className={clsx('inline-flex items-center gap-2 rounded-xl border py-1.5 pr-3 pl-1.5 text-[12.5px] font-semibold transition', on ? 'shadow-card' : 'border-tt-line text-tt-slate hover:border-tt-periwinkle')}
                    style={on ? { borderColor: v.color, color: v.color, background: v.tint } : undefined}
                  >
                    <DomainIcon id={d.id} size="sm" />
                    {d.name}
                  </button>
                )
              })}
            </div>
          </div>
        )}

        <div className="mt-4 grid gap-3 sm:grid-cols-[1fr_auto] sm:items-end">
          <label className="block">
            <span className="mb-1 flex items-center gap-1.5 text-[12px] font-semibold text-tt-slate">
              <KeyRound size={13} /> {user ? 'Reset password (leave empty to keep)' : 'Initial password'}
            </span>
            <input value={password} onChange={(e) => setPassword(e.target.value)} className={clsx(input, 'font-mono')} placeholder={user ? '••••••••' : ''} />
          </label>
          <button type="button" onClick={() => setPassword(randomPassword())} className="rounded-xl px-3 py-2.5 text-[12.5px] font-semibold text-tt-electric ring-1 ring-tt-line hover:bg-tt-mist">
            Generate
          </button>
        </div>
        {!user && <p className="mt-1.5 text-[11.5px] text-tt-slate">Share it with the person securely; they can change it after signing in.</p>}

        {user && !isSelf && (
          <label className="mt-4 flex cursor-pointer items-center justify-between rounded-xl border border-tt-line px-4 py-3 select-none">
            <span>
              <span className="block text-[13px] font-semibold text-tt-navy">Account active</span>
              <span className="block text-[11.5px] text-tt-slate">Disabling signs the person out immediately</span>
            </span>
            <button type="button" onClick={() => setActive((a) => !a)} className={clsx('relative h-5 w-9 rounded-full transition', active ? 'bg-tt-teal' : 'bg-tt-line')} aria-pressed={active}>
              <span className={clsx('absolute top-0.5 h-4 w-4 rounded-full bg-white shadow transition-all', active ? 'left-[18px]' : 'left-0.5')} />
            </button>
          </label>
        )}

        {error && <div className="mt-4 rounded-xl border border-tt-ember/30 bg-[#fdf0ea] px-3.5 py-2.5 text-[13px] text-[#8a3510]">{error}</div>}

        <div className="mt-6 flex justify-end gap-2">
          <button onClick={onClose} className="rounded-xl px-4 py-2.5 text-[13.5px] font-semibold text-tt-slate hover:bg-tt-mist">
            Cancel
          </button>
          <button
            onClick={save}
            disabled={busy || (!user && (!username.trim() || password.length < 8))}
            className="bg-tt-electric-gradient inline-flex items-center gap-2 rounded-xl px-5 py-2.5 font-display text-[13.5px] font-semibold text-white disabled:opacity-50"
          >
            {busy && <LoaderCircle size={15} className="animate-spin" />}
            {user ? 'Save changes' : 'Create account'}
          </button>
        </div>
      </motion.div>
    </>
  )
}
