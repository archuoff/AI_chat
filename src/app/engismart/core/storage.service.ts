import { Injectable, inject } from '@angular/core';
import { SessionService } from './session.service';
import type { Session, UIMessage } from './types';

export const uid = (): string =>
  typeof crypto !== 'undefined' && 'randomUUID' in crypto ? crypto.randomUUID() : `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;

/**
 * Per-browser conveniences only (session list + rendered messages with their sources), kept per user so a shared computer never shows
 * one user's conversations to another. The server keeps the authoritative conversation memory (also per user).
 */
@Injectable({ providedIn: 'root' })
export class StorageService {
  private readonly session = inject(SessionService);
  private scope = () => `u${this.session.me()?.id ?? 'anon'}`;
  private read<T>(key: string, fallback: T): T {
    try {
      const raw = localStorage.getItem(key);
      return raw ? (JSON.parse(raw) as T) : fallback;
    } catch {
      return fallback;
    }
  }
  private write(key: string, value: unknown) {
    try {
      localStorage.setItem(key, JSON.stringify(value));
    } catch { /* storage full or blocked */ }
  }
  pref = <T>(name: string, fallback: T) => this.read<T>(`engismart.pref.${name}`, fallback);
  setPref = (name: string, value: unknown) => this.write(`engismart.pref.${name}`, value);
  sessions = () => this.read<Session[]>(`engismart.${this.scope()}.sessions`, []);
  saveSessions = (s: Session[]) => this.write(`engismart.${this.scope()}.sessions`, s);
  messages = (id: string) => this.read<UIMessage[] | null>(`engismart.${this.scope()}.messages.${id}`, null);
  saveMessages = (id: string, m: UIMessage[]) => this.write(`engismart.${this.scope()}.messages.${id}`, m);
  removeMessages(id: string) {
    try {
      localStorage.removeItem(`engismart.${this.scope()}.messages.${id}`);
    } catch { /* ignore */ }
  }
}
