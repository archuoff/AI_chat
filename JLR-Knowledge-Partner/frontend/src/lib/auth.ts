// Signed-in session: JWT + user profile. Kept in localStorage so a page refresh stays signed in;
// the server re-validates the token on every request (expiry, revocation, role).
export type Role = 'user' | 'superuser' | 'developer'
export type AuthUser = { id: number; username: string; display_name: string; role: Role; domains: string[] }
type Stored = { token: string; user: AuthUser; expiresAt: number }

const KEY = 'tt-kg.auth'
let current: Stored | null = load()
const listeners = new Set<() => void>()

function load(): Stored | null {
  try {
    const raw = localStorage.getItem(KEY)
    const s = raw ? (JSON.parse(raw) as Stored) : null
    return s && s.expiresAt > Date.now() ? s : null
  } catch {
    return null
  }
}

function save(s: Stored | null) {
  current = s
  try {
    if (s) localStorage.setItem(KEY, JSON.stringify(s))
    else localStorage.removeItem(KEY)
  } catch {
    /* storage blocked: session lasts until refresh */
  }
  listeners.forEach((l) => l())
}

export const auth = {
  get: () => current,
  token: () => current?.token ?? null,
  user: () => current?.user ?? null,
  set: (token: string, user: AuthUser, expiresInS: number) => save({ token, user, expiresAt: Date.now() + expiresInS * 1000 }),
  setToken: (token: string, expiresInS: number) => current && save({ ...current, token, expiresAt: Date.now() + expiresInS * 1000 }),
  clear: () => save(null),
  subscribe: (fn: () => void) => {
    listeners.add(fn)
    return () => listeners.delete(fn)
  },
}

export const ROLE_LABEL: Record<Role, string> = { user: 'User', superuser: 'Super user', developer: 'Developer' }
