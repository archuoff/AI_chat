import { HttpClient, HttpErrorResponse, HttpEventType, HttpParams } from '@angular/common/http';
import { inject, Injectable } from '@angular/core';
import { firstValueFrom, Observable } from 'rxjs';
import { baseOf, CHAT_BASE } from './env';
import type {
  ChatFinal, ChunkInfo, DescribeJob, DocImage, DocImages, DocumentInfo, Domain, DomainSuggestion, ExcelPreview, Health, ImageCounts,
  ImagesSummary, IngestResult, ManagedUser, Me, ParseOptions, StreamEvent, UploadCheck, UsageSummary,
} from './types';

/** The platform's answer envelope. */
type Envelope<T> = { status: boolean; data: T; message: string; error: string | null };

/** An error with the readable message from the envelope. */
export class ApiError extends Error {
  constructor(message: string, readonly status: number) {
    super(message);
  }
}

/** The readable text of an error body: our envelope {message}, or FastAPI's {detail: "text" | {message} | [{msg}]} (platform guards, bad bodies). */
function messageOf(body: unknown): string {
  if (!body || typeof body !== 'object') return '';
  const b = body as { message?: unknown; detail?: unknown };
  if (typeof b.message === 'string' && b.message) return b.message;
  const d = b.detail;
  if (typeof d === 'string') return d;
  if (d && typeof d === 'object' && !Array.isArray(d) && typeof (d as { message?: unknown }).message === 'string') return (d as { message: string }).message;
  if (Array.isArray(d) && d.length) {
    const first = d[0] as { msg?: string; loc?: unknown[] };
    const where = (first.loc ?? []).filter((x) => x !== 'body').join('.');
    return `Invalid request${where ? ` (${where})` : ''}: ${first.msg ?? 'bad value'}`;
  }
  return '';
}

function toApiError(e: unknown): ApiError {
  if (e instanceof ApiError) return e;
  if (e instanceof HttpErrorResponse) {
    let body: unknown = e.error;
    if (typeof body === 'string' && body) {
      try { body = JSON.parse(body); } catch { /* not JSON */ }
    }
    const text = messageOf(body);
    if (text) return new ApiError(text, e.status);
    return new ApiError(e.status ? `${e.status} ${e.statusText}` : 'The server could not be reached', e.status);
  }
  return new ApiError((e as Error)?.message ?? String(e), 0);
}

/**
 * All calls to the Engismart backend. Only Angular's HttpClient is used: the host's HTTP interceptor adds the platform token
 * (this remote has no login logic), including for the chat stream and the picture files.
 */
@Injectable({ providedIn: 'root' })
export class ApiService {
  private readonly http = inject(HttpClient);
  private lastWarmup = 0;

  private async call<T>(obs: Observable<Envelope<T>>): Promise<T> {
    try {
      const r = await firstValueFrom(obs);
      if (!r.status) throw new ApiError(r.message || 'The request failed', 200);
      return r.data;
    } catch (e) {
      throw toApiError(e);
    }
  }

  private get<T>(path: string, params?: Record<string, string | number | boolean | undefined>) {
    let p = new HttpParams();
    for (const [k, v] of Object.entries(params ?? {})) if (v !== undefined) p = p.set(k, String(v));
    return this.call(this.http.get<Envelope<T>>(`${baseOf(path)}${path}`, { params: p }));
  }
  private send<T>(method: 'POST' | 'PUT' | 'PATCH' | 'DELETE', path: string, body?: unknown) {
    return this.call(this.http.request<Envelope<T>>(method, `${baseOf(path)}${path}`, { body: body ?? (method === 'DELETE' ? undefined : {}) }));
  }

  // ---- who am I
  me = () => this.get<Me>('/me');
  health = () => this.get<Health>('/health');
  domains = () => this.get<Domain[]>('/domains');

  // ---- users & usage (developer)
  users = () => this.get<ManagedUser[]>('/users');
  lookupUsers = (q: string) => this.get<ManagedUser[]>('/users/lookup', { q });
  setUserDomains = (id: number, domains: string[]) => this.send<{ user_id: number; domains: string[] }>('PUT', `/users/${id}/domains`, { domains });
  usage = (days = 30) => this.get<UsageSummary>('/usage/summary', { days });

  // ---- knowledge (developer)
  documents = () => this.get<DocumentInfo[]>('/documents');
  chunks = (docId: string, limit = 200) => this.get<ChunkInfo[]>(`/documents/${docId}/chunks`, { limit });
  deleteDocument = (docId: string) => this.send('DELETE', `/documents/${docId}`);
  setDomain = (docId: string, domain: string) => this.send<DocumentInfo>('PATCH', `/documents/${docId}`, { domain });
  setConfidential = (docId: string, confidential: boolean) => this.send<DocumentInfo>('PATCH', `/documents/${docId}/access`, { confidential });
  bulkDomain = (docIds: string[], domain: string) =>
    this.send<{ updated: string[]; missing: string[] }>('POST', '/documents/bulk-domain', { doc_ids: docIds, domain });
  suggestDomain = (docId: string) => this.send<DomainSuggestion>('POST', `/documents/${docId}/suggest-domain`);
  excelPreview = (docId: string, sheet?: string) => this.get<ExcelPreview>(`/documents/${docId}/excel-preview`, { sheet });
  saveParseOptions = (docId: string, parse_options: ParseOptions) => this.send<IngestResult>('PUT', `/documents/${docId}/parse-options`, { parse_options });
  reprocess = (docId: string) => this.send<IngestResult>('POST', `/documents/${docId}/reprocess`);
  restoreDocument = (docId: string) => this.send<{ restored: string }>('POST', `/documents/${docId}/restore`);

  checkUpload(file: File, domain: string): Promise<UploadCheck> {
    const fd = new FormData();
    fd.append('file', file);
    fd.append('domain', domain);
    return this.call(this.http.post<Envelope<UploadCheck>>(`${baseOf('/documents/check')}/documents/check`, fd));
  }
  async commitUpload(req: { check_id: string; intent: 'new' | 'update'; replaces?: string; domain: string; metadata: Record<string, unknown>; force: boolean; allow_duplicate: boolean }): Promise<IngestResult> {
    const res = await this.send<{ results: IngestResult[] }>('POST', '/documents/commit', req);
    return res.results[0];
  }

  // ---- pictures (developer to manage; the file follows the document's access rules)
  imagesSummary = () => this.get<ImagesSummary>('/images/summary');
  docImages = (docId: string) => this.get<DocImages>(`/documents/${docId}/images`);
  extractImages = (docId: string) => this.send<ImageCounts>('POST', `/documents/${docId}/images/extract`, {});
  setImageIncluded = (id: string, included: boolean) => this.send<DocImage>('PATCH', `/images/${id}`, { included });
  describeImages = (body: { doc_ids?: string[]; image_ids?: string[] }) => this.send<DescribeJob>('POST', '/images/describe', body);
  describeJob = () => this.get<DescribeJob>('/images/job');
  cancelDescribe = () => this.send<DescribeJob>('POST', '/images/job/cancel', {});
  async imageBlob(id: string, thumb: boolean): Promise<Blob> {
    try {
      return await firstValueFrom(this.http.get(`${CHAT_BASE}/images/${id}/file`, { params: { thumb }, responseType: 'blob' }));
    } catch (e) {
      throw toApiError(e);
    }
  }

  // ---- chat (every role)
  /** Pre-open the backend's Azure connections while the user types (fire and forget, throttled). */
  warmup(): void {
    const now = Date.now();
    if (now - this.lastWarmup < 3000) return;
    this.lastWarmup = now;
    this.http.post(`${CHAT_BASE}/warmup`, {}).subscribe({ error: () => undefined });
  }
  history = (sessionId: string) => this.get<{ role: 'user' | 'assistant'; content: string }[]>(`/chat/${encodeURIComponent(sessionId)}/messages`);
  deleteSession = (sessionId: string) => this.send('DELETE', `/chat/${encodeURIComponent(sessionId)}`);
  /** Edit and send: the server forgets every question after the first `turns` ones before the edited question is sent. */
  rewind = (sessionId: string, turns: number) => this.send<{ kept_messages: number }>('POST', `/chat/${encodeURIComponent(sessionId)}/rewind`, { turns });

  /**
   * POST /chat/stream (server-sent events) with HttpClient so the host adds the token like for every other call.
   * Each complete event is passed to `onEvent`; resolves with the final payload.
   */
  streamChat(body: { session_id: string; message: string; filters?: Record<string, unknown> | null; images?: string[] },
             onEvent: (e: StreamEvent) => void, signal?: AbortSignal): Promise<ChatFinal | null> {
    return new Promise((resolve, reject) => {
      let consumed = 0;
      let final: ChatFinal | null = null;
      const feed = (text: string, last: boolean) => {
        let idx: number;
        while ((idx = text.indexOf('\n\n', consumed)) >= 0) {
          const raw = text.slice(consumed, idx);
          consumed = idx + 2;
          const data = raw.split('\n').filter((l) => l.startsWith('data:')).map((l) => l.slice(5).trimStart()).join('\n');
          if (!data) continue;
          const event = JSON.parse(data) as StreamEvent;
          if (event.type === 'final') final = event;
          onEvent(event);
        }
        if (last && text.slice(consumed).trim()) consumed = text.length;
      };
      const sub = this.http.post(`${CHAT_BASE}/chat/stream`, body, { observe: 'events', reportProgress: true, responseType: 'text' }).subscribe({
        next: (ev) => {
          if (ev.type === HttpEventType.DownloadProgress) feed((ev as { partialText?: string }).partialText ?? '', false);
          else if (ev.type === HttpEventType.Response) {
            feed(String(ev.body ?? ''), true);
            resolve(final);
          }
        },
        error: (e) => reject(toApiError(e)),
      });
      signal?.addEventListener('abort', () => {
        sub.unsubscribe();
        reject(new DOMException('aborted', 'AbortError'));
      });
    });
  }
}
