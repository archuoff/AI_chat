// Signed-in session: JWT + user profile. "Remember me" keeps it in localStorage (survives closing the browser);
// otherwise it lives in sessionStorage (survives a refresh, ends when the tab is closed).
// The server re-validates the token on every request (expiry, revocation, role).
export type Role = 'user' | 'superuser' | 'developer'
export type AuthUser = { id: number; username: string; display_name: string; role: Role; domains: string[] }
type Stored = { token: string; user: AuthUser; expiresAt: number }

const KEY = 'tt-kg.auth'
let remembered = true
let current: Stored | null = load()
const listeners = new Set<() => void>()

function load(): Stored | null {
  for (const [store, persist] of [[sessionStorage, false], [localStorage, true]] as const) {
    try {
      const raw = store.getItem(KEY)
      const s = raw ? (JSON.parse(raw) as Stored) : null
      if (s && s.expiresAt > Date.now()) {
        remembered = persist
        return s
      }
    } catch {
      /* storage blocked */
    }
  }
  return null
}

function save(s: Stored | null) {
  current = s
  try {
    localStorage.removeItem(KEY)
    sessionStorage.removeItem(KEY)
    if (s) (remembered ? localStorage : sessionStorage).setItem(KEY, JSON.stringify(s))
  } catch {
    /* storage blocked: session lasts until refresh */
  }
  listeners.forEach((l) => l())
}

export const auth = {
  get: () => current,
  token: () => current?.token ?? null,
  user: () => current?.user ?? null,
  set: (token: string, user: AuthUser, expiresInS: number, remember = true) => {
    remembered = remember
    save({ token, user, expiresAt: Date.now() + expiresInS * 1000 })
  },
  setToken: (token: string, expiresInS: number) => current && save({ ...current, token, expiresAt: Date.now() + expiresInS * 1000 }),
  clear: () => save(null),
  subscribe: (fn: () => void) => {
    listeners.add(fn)
    return () => listeners.delete(fn)
  },
}

export const ROLE_LABEL: Record<Role, string> = { user: 'User', superuser: 'Super user', developer: 'Developer' }
