import clsx from 'clsx'
import { Library, MessagesSquare, PanelLeftClose, PanelLeftOpen, Plus, Trash, UsersRound, X } from 'lucide-react'
import { AnimatePresence, motion } from 'motion/react'
import type { AuthUser } from '../lib/auth'
import { timeAgo } from '../lib/format'
import type { Session } from '../lib/types'
import { AccountMenu } from './AccountMenu'
import { Brand, JlrLogo } from './Brand'

export type View = 'chat' | 'manage' | 'users'

type Props = {
  user: AuthUser
  view: View
  onView: (v: View) => void
  sessions: Session[]
  activeId: string | null
  onSelect: (id: string) => void
  onNew: () => void
  onDelete: (id: string) => void
  open: boolean
  onClose: () => void
  collapsed: boolean
  onToggleCollapsed: () => void
}

const NAV = [
  { id: 'chat' as const, label: 'Assistant', Icon: MessagesSquare, developer: false },
  { id: 'manage' as const, label: 'Manage knowledge', Icon: Library, developer: true },
  { id: 'users' as const, label: 'Users & usage', Icon: UsersRound, developer: true },
]

export function Sidebar(p: Props) {
  // the rail (collapsed) only applies on desktop; the mobile drawer is always full width
  const rail = p.collapsed
  const nav = NAV.filter((n) => !n.developer || p.user.role === 'developer')
  return (
    <>
      <AnimatePresence>
        {p.open && (
          <motion.div
            className="fixed inset-0 z-30 bg-tt-midnight/50 lg:hidden"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={p.onClose}
          />
        )}
      </AnimatePresence>
      <aside
        className={clsx(
          'bg-tt-sidebar fixed inset-y-0 left-0 z-40 flex w-[272px] shrink-0 flex-col overflow-hidden text-white transition-transform duration-300 ease-out lg:static lg:translate-x-0 lg:transition-none',
          p.open ? 'translate-x-0' : '-translate-x-full',
          rail && 'lg:w-[76px]',
        )}
      >
        {/* header */}
        <div className={clsx('flex items-center px-4 pt-5 pb-4', rail ? 'lg:flex-col lg:gap-3 lg:px-0' : 'justify-between')}>
          <div className={clsx(rail && 'lg:hidden')}>
            <Brand />
          </div>
          {rail && (
            <div className="hidden lg:block">
              <JlrLogo className="h-[26px] w-auto text-white" />
            </div>
          )}
          <button
            onClick={p.onToggleCollapsed}
            className="hidden rounded-lg p-1.5 text-white/55 transition hover:bg-white/10 hover:text-white lg:block"
            title={rail ? 'Expand sidebar' : 'Collapse sidebar'}
            aria-label={rail ? 'Expand sidebar' : 'Collapse sidebar'}
          >
            {rail ? <PanelLeftOpen size={18} /> : <PanelLeftClose size={18} />}
          </button>
          <button className="rounded-lg p-1.5 text-white/60 hover:bg-white/10 lg:hidden" onClick={p.onClose} aria-label="Close menu">
            <X size={18} />
          </button>
        </div>

        {/* new conversation */}
        <div className={clsx('px-4', rail && 'lg:px-3.5')}>
          <button
            onClick={p.onNew}
            title="New conversation"
            className={clsx(
              'group flex w-full items-center justify-center gap-2 rounded-xl bg-white font-display text-[14px] font-semibold text-tt-electric shadow-[0_8px_24px_-8px_rgba(0,0,179,0.6)] transition hover:-translate-y-px hover:shadow-[0_12px_28px_-8px_rgba(18,198,179,0.55)]',
              rail ? 'h-11 px-4 lg:px-0' : 'h-11 px-4',
            )}
          >
            <Plus size={18} strokeWidth={2.5} className="shrink-0 transition group-hover:rotate-90" />
            <span className={clsx(rail && 'lg:hidden')}>New conversation</span>
          </button>
        </div>

        {/* navigation */}
        <nav className={clsx('mt-5 space-y-1 px-3', rail && 'lg:px-3.5')}>
          {nav.map(({ id, label, Icon }) => (
            <button
              key={id}
              onClick={() => p.onView(id)}
              title={label}
              className={clsx(
                'relative flex w-full items-center gap-3 rounded-xl py-2.5 text-[14px] font-medium transition',
                rail ? 'px-3.5 lg:justify-center lg:px-0' : 'px-3.5',
                p.view === id ? 'bg-white/12 text-white' : 'text-white/65 hover:bg-white/6 hover:text-white',
              )}
            >
              {p.view === id && <motion.span layoutId="nav-pill" className="absolute inset-y-2 left-0 w-[3px] rounded-full bg-tt-teal" />}
              <Icon size={19} className="shrink-0" />
              <span className={clsx('truncate', rail && 'lg:hidden')}>{label}</span>
            </button>
          ))}
        </nav>

        {/* recent conversations */}
        <div className={clsx('mt-6 flex min-h-0 flex-1 flex-col', rail && 'lg:hidden')}>
          <div className="flex items-center justify-between px-5">
            <span className="font-display text-[11px] font-semibold tracking-[0.18em] text-white/40">RECENT</span>
            <span className="text-[11px] text-white/35">{p.sessions.length}</span>
          </div>
          <div className="scrollbar-thin mt-2 flex-1 space-y-0.5 overflow-y-auto px-3 pb-4">
            {p.sessions.length === 0 && <p className="px-3 py-2 text-[13px] leading-relaxed text-white/40">Your conversations will appear here.</p>}
            <AnimatePresence initial={false}>
              {p.sessions.map((s) => (
                <motion.div
                  key={s.id}
                  layout
                  initial={{ opacity: 0, x: -8 }}
                  animate={{ opacity: 1, x: 0 }}
                  exit={{ opacity: 0, height: 0 }}
                  className={clsx(
                    'group flex cursor-pointer items-center gap-2 rounded-lg px-3 py-2 transition',
                    s.id === p.activeId && p.view === 'chat' ? 'bg-white/10' : 'hover:bg-white/6',
                  )}
                  onClick={() => p.onSelect(s.id)}
                >
                  <div className="min-w-0 flex-1">
                    <div className="truncate text-[13.5px] text-white/90">{s.title}</div>
                    <div className="text-[11px] text-white/40">{timeAgo(s.updatedAt)}</div>
                  </div>
                  <button
                    onClick={(e) => {
                      e.stopPropagation()
                      p.onDelete(s.id)
                    }}
                    className="rounded-md p-1 text-white/40 opacity-0 transition group-hover:opacity-100 hover:bg-white/10 hover:text-white"
                    aria-label="Delete conversation"
                  >
                    <Trash size={14} />
                  </button>
                </motion.div>
              ))}
            </AnimatePresence>
          </div>
        </div>
        {rail && <div className="hidden flex-1 lg:block" />}
        <AccountMenu user={p.user} rail={rail} />
      </aside>
    </>
  )
}
