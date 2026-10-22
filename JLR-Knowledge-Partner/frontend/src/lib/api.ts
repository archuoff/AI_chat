import { auth, type AuthUser } from './auth'
import type {
  ChatFinal,
  ChunkInfo,
  DescribeJob,
  DocImage,
  DocImages,
  DocumentInfo,
  ImageCounts,
  ImagesSummary,
  Domain,
  DomainSuggestion,
  ExcelPreview,
  Health,
  IngestResult,
  ManagedUser,
  ParseOptions,
  StreamEvent,
  UsageSummary,
} from './types'

/** fetch with the signed-in user's JWT; a 401 (expired / revoked) signs out. */
async function request(path: string, init: RequestInit = {}): Promise<Response> {
  const headers = new Headers(init.headers)
  const token = auth.token()
  if (token) headers.set('Authorization', `Bearer ${token}`)
  const res = await fetch(path, { ...init, headers })
  if (res.status === 401 && token && !path.startsWith('/api/auth/login')) auth.clear()
  return res
}

const jsonBody = (method: string, body: unknown): RequestInit => ({
  method,
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(body),
})

async function json<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let detail = `${res.status} ${res.statusText}`
    try {
      const body = await res.json()
      if (body?.detail) detail = typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail)
    } catch {
      /* body was not JSON */
    }
    throw new Error(detail)
  }
  return res.json() as Promise<T>
}

const get = <T,>(path: string) => request(path).then((r) => json<T>(r))
const send = <T,>(method: string, path: string, body?: unknown) =>
  request(path, body === undefined ? { method } : jsonBody(method, body)).then((r) => json<T>(r))

export const api = {
  // ---- auth
  login: async (username: string, password: string) => {
    const r = await json<{ access_token: string; expires_in: number; user: AuthUser }>(
      await request('/api/auth/login', jsonBody('POST', { username, password })),
    )
    auth.set(r.access_token, r.user, r.expires_in)
    return r.user
  },
  changePassword: async (current_password: string, new_password: string) => {
    const r = await send<{ access_token: string; expires_in: number }>('POST', '/api/auth/change-password', { current_password, new_password })
    auth.setToken(r.access_token, r.expires_in)
  },

  // ---- users & usage (developer)
  users: () => get<ManagedUser[]>('/api/users'),
  createUser: (body: { username: string; display_name: string; password: string; role: string; domains: string[] }) =>
    send<ManagedUser>('POST', '/api/users', body),
  updateUser: (id: number, body: Partial<{ display_name: string; role: string; domains: string[]; is_active: boolean; password: string }>) =>
    send<ManagedUser>('PATCH', `/api/users/${id}`, body),
  deleteUser: (id: number) => send('DELETE', `/api/users/${id}`),
  usage: (days = 30) => get<UsageSummary>(`/api/usage/summary?days=${days}`),

  // ---- knowledge (developer)
  health: () => get<Health>('/api/health'),
  documents: () => get<DocumentInfo[]>('/api/documents'),
  chunks: (docId: string, limit = 200) => get<ChunkInfo[]>(`/api/documents/${docId}/chunks?limit=${limit}`),
  deleteDocument: (docId: string) => send('DELETE', `/api/documents/${docId}`),
  domains: () => get<Domain[]>('/api/domains'),

  // ---- document pictures (developer; the picture file follows the document's access rules)
  imagesSummary: () => get<ImagesSummary>('/api/images/summary'),
  docImages: (docId: string) => get<DocImages>(`/api/documents/${docId}/images`),
  extractImages: (docId: string) => send<ImageCounts>('POST', `/api/documents/${docId}/images/extract`, {}),
  setImageIncluded: (id: string, included: boolean) => send<DocImage>('PATCH', `/api/images/${id}`, { included }),
  describeImages: (body: { doc_ids?: string[]; image_ids?: string[] }) => send<DescribeJob>('POST', '/api/images/describe', body),
  describeJob: () => get<DescribeJob>('/api/images/job'),
  cancelDescribe: () => send<DescribeJob>('POST', '/api/images/job/cancel', {}),
  imageBlob: async (id: string, thumb: boolean) => {
    const r = await request(`/api/images/${id}/file?thumb=${thumb}`)
    if (!r.ok) throw new Error(`picture ${r.status}`)
    return r.blob()
  },
  setDomain: (docId: string, domain: string) => send<DocumentInfo>('PATCH', `/api/documents/${docId}`, { domain }),
  setConfidential: (docId: string, confidential: boolean) =>
    send<DocumentInfo>('PATCH', `/api/documents/${docId}/access`, { confidential }),
  bulkDomain: (docIds: string[], domain: string) =>
    send<{ updated: string[]; missing: string[] }>('POST', '/api/documents/bulk-domain', { doc_ids: docIds, domain }),
  suggestDomain: (docId: string) => send<DomainSuggestion>('POST', `/api/documents/${docId}/suggest-domain`),
  excelPreview: (docId: string, sheet?: string) =>
    get<ExcelPreview>(`/api/documents/${docId}/excel-preview${sheet ? `?sheet=${encodeURIComponent(sheet)}` : ''}`),
  saveParseOptions: (docId: string, parse_options: ParseOptions) =>
    send<IngestResult>('PUT', `/api/documents/${docId}/parse-options`, { parse_options }),
  reprocess: (docId: string) => send<IngestResult>('POST', `/api/documents/${docId}/reprocess`),

  upload: async (file: File, meta: Record<string, unknown>, force: boolean, domain = ''): Promise<IngestResult> => {
    const fd = new FormData()
    fd.append('files', file)
    fd.append('metadata', JSON.stringify(meta))
    fd.append('force', String(force))
    fd.append('domain', domain)
    const res = await json<{ results: IngestResult[] }>(await request('/api/documents', { method: 'POST', body: fd }))
    return res.results[0]
  },

  // ---- chat (every role)
  /** Pre-open the backend's Azure connections while the user types (fire and forget, throttled). */
  warmup: (() => {
    let last = 0
    return () => {
      const now = Date.now()
      if (now - last < 3000 || !auth.token()) return
      last = now
      request('/api/warmup', { method: 'POST' }).catch(() => {})
    }
  })(),
  history: (sessionId: string) =>
    get<{ role: 'user' | 'assistant'; content: string }[]>(`/api/chat/${encodeURIComponent(sessionId)}/messages`),
  deleteSession: (sessionId: string) => send('DELETE', `/api/chat/${encodeURIComponent(sessionId)}`),
}

/** POST /api/chat/stream and dispatch each server-sent event. Resolves with the final payload. */
export async function streamChat(
  body: { session_id: string; message: string; filters?: Record<string, unknown> | null; images?: string[] },
  onEvent: (e: StreamEvent) => void,
  signal?: AbortSignal,
): Promise<ChatFinal | null> {
  const res = await request('/api/chat/stream', { ...jsonBody('POST', body), signal })
  if (!res.ok || !res.body) {
    await json(res)
    return null
  }
  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  let final: ChatFinal | null = null
  for (;;) {
    const { value, done } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    let idx: number
    while ((idx = buffer.indexOf('\n\n')) >= 0) {
      const raw = buffer.slice(0, idx)
      buffer = buffer.slice(idx + 2)
      const data = raw
        .split('\n')
        .filter((l) => l.startsWith('data:'))
        .map((l) => l.slice(5).trimStart())
        .join('\n')
      if (!data) continue
      const event = JSON.parse(data) as StreamEvent
      if (event.type === 'final') final = event
      onEvent(event)
    }
  }
  return final
}
