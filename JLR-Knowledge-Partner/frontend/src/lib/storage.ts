import { auth } from './auth'
import type { Session, UIMessage } from './types'

// Per-browser conveniences only (session list + rendered messages with their sources), kept per
// signed-in user so a shared computer never shows one user's conversations to another.
// The server keeps the authoritative conversation memory (also per user).
const scope = () => `u${auth.user()?.id ?? 'anon'}`
const SESSIONS = () => `tt-kg.${scope()}.sessions`
const MSGS = (id: string) => `tt-kg.${scope()}.messages.${id}`

function read<T>(key: string, fallback: T): T {
  try {
    const raw = localStorage.getItem(key)
    return raw ? (JSON.parse(raw) as T) : fallback
  } catch {
    return fallback
  }
}

function write(key: string, value: unknown) {
  try {
    localStorage.setItem(key, JSON.stringify(value))
  } catch {
    /* storage full or blocked */
  }
}

export const storage = {
  pref: <T,>(name: string, fallback: T) => read<T>(`tt-kg.pref.${name}`, fallback),
  setPref: (name: string, value: unknown) => write(`tt-kg.pref.${name}`, value),
  sessions: () => read<Session[]>(SESSIONS(), []),
  saveSessions: (s: Session[]) => write(SESSIONS(), s),
  messages: (id: string) => read<UIMessage[] | null>(MSGS(id), null),
  saveMessages: (id: string, m: UIMessage[]) => write(MSGS(id), m),
  removeMessages: (id: string) => {
    try {
      localStorage.removeItem(MSGS(id))
    } catch {
      /* ignore */
    }
  },
}

export const uid = () =>
  typeof crypto !== 'undefined' && 'randomUUID' in crypto
    ? crypto.randomUUID()
    : `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`
