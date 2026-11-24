import { ChangeDetectionStrategy, Component, computed, DestroyRef, effect, ElementRef, inject, OnInit, signal, untracked, viewChild } from '@angular/core';
import { ApiService } from '../core/api.service';
import type { Attachment } from '../core/images';
import { SessionService } from '../core/session.service';
import { StorageService, uid } from '../core/storage.service';
import type { ServerTurn, Session, UIMessage } from '../core/types';
import { IconComponent } from '../ui/icon.component';
import { buildFilters, ComposerComponent } from './composer.component';
import { MessageComponent } from './message.component';
import { SourcesPanelComponent } from './sources-panel.component';
import { WelcomeComponent } from './welcome.component';

const WIDE = '(min-width: 1180px)';

@Component({
  selector: 'eng-chat-page',
  imports: [IconComponent, ComposerComponent, MessageComponent, SourcesPanelComponent, WelcomeComponent],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './chat.page.html',
  styleUrl: './chat.page.scss',
})
export class ChatPage implements OnInit {
  private readonly api = inject(ApiService);
  private readonly storage = inject(StorageService);
  readonly session = inject(SessionService);
  private readonly destroyRef = inject(DestroyRef);

  readonly sessions = signal<Session[]>([]);
  readonly activeId = signal<string>('');
  readonly messages = signal<UIMessage[]>([]);
  readonly busy = signal(false);
  readonly domain = signal('all');
  readonly domainOptions = signal<string[]>(['all']);
  readonly activeMsg = signal<string | null>(null);
  readonly highlight = signal<number | null>(null);
  readonly sourcesOpen = signal(false);
  readonly wide = signal(typeof matchMedia === 'function' ? matchMedia(WIDE).matches : true);
  readonly awayFromBottom = signal(false);
  readonly listOpen = signal(false);
  readonly scroller = viewChild<ElementRef<HTMLElement>>('scroller');
  private abort: AbortController | null = null;
  private pinned = true;

  readonly panelMsg = computed(() => {
    const assistants = this.messages().filter((m) => m.role === 'assistant');
    return assistants.find((m) => m.id === this.activeMsg()) ?? assistants.at(-1);
  });
  readonly title = computed(() => this.sessions().find((s) => s.id === this.activeId())?.title ?? 'New conversation');
  readonly realDomains = computed(() => this.domainOptions().filter((d) => d !== 'all'));

  constructor() {
    effect(() => {
      const id = this.activeId();
      if (!id) return;
      untracked(() => this.openSession(id));
    });
    effect(() => {
      const msgs = this.messages();
      const el = untracked(() => this.scroller()?.nativeElement);
      if (!el) return;
      queueMicrotask(() => {
        if (msgs.length === 0) el.scrollTo({ top: 0 });
        else if (this.pinned) el.scrollTo({ top: el.scrollHeight });
      });
    });
    effect(() => {
      if (!this.busy() && this.messages().length) untracked(() => this.storage.saveMessages(this.activeId(), this.messages()));
    });
    effect(() => this.storage.saveSessions(this.sessions()));
  }

  ngOnInit() {
    this.sessions.set(this.storage.sessions()); // shown until the server answers; the server's list replaces it
    this.sourcesOpen.set(this.wide() && this.storage.pref('sourcesOpen', true));
    this.activeId.set(this.sessions()[0]?.id ?? uid());
    this.loadSessions();
    this.api.domains().then((ds) => this.domainOptions.set(['all', ...ds.map((d) => d.id).filter((id) => id !== 'unassigned')])).catch(() => undefined);
    if (typeof matchMedia === 'function') {
      const mq = matchMedia(WIDE);
      const on = () => this.wide.set(mq.matches);
      mq.addEventListener('change', on);
      this.destroyRef.onDestroy(() => mq.removeEventListener('change', on));
    }
    this.destroyRef.onDestroy(() => this.abort?.abort());
  }

  /** The conversation list from the server. Offline, the list stays as it was (the browser copy). */
  private loadSessions() {
    this.api.sessions().then((list) => {
      this.sessions.set(list.map((s) => ({ id: s.session_id, title: s.title, updatedAt: Date.parse(s.updated_on) || Date.now() })));
    }).catch(() => undefined);
  }

  /** Opens a conversation: the server's copy (questions, answers, sources) is the truth; the browser copy shows while it loads. */
  private openSession(id: string) {
    this.abort?.abort();
    this.busy.set(false);
    this.highlight.set(null);
    this.activeMsg.set(null);
    const cached = this.storage.messages(id);
    this.messages.set(cached ? cached.map((m) => ({ ...m, streaming: false })) : []);
    this.api.history(id).then((turns) => {
      if (this.activeId() !== id || this.busy()) return; // the user moved on, or is asking a new question here
      this.messages.set(this.toMessages(turns));
    }).catch(() => undefined); // offline: the browser copy stays on screen
  }

  /** One stored turn is one question and one answer. */
  private toMessages(turns: ServerTurn[]): UIMessage[] {
    return turns.flatMap((t) => [
      { id: uid(), role: 'user' as const, content: t.question },
      { id: uid(), role: 'assistant' as const, content: t.answer, sources: t.sources ?? [], mode: t.mode ?? null },
    ]);
  }

  select(id: string) {
    this.activeId.set(id);
    this.listOpen.set(false);
  }
  newChat() {
    this.activeId.set(uid());
    this.listOpen.set(false);
  }
  remove(id: string, ev: Event) {
    ev.stopPropagation();
    this.api.deleteSession(id).catch(() => undefined);
    this.storage.removeMessages(id);
    this.sessions.update((cur) => cur.filter((s) => s.id !== id));
    if (id === this.activeId()) this.activeId.set(uid());
  }
  private touch(id: string, question: string) {
    this.sessions.update((cur) => {
      const existing = cur.find((s) => s.id === id);
      const title = existing?.title ?? (question.length > 60 ? `${question.slice(0, 57)}…` : question);
      return [{ id, title, updatedAt: Date.now() }, ...cur.filter((s) => s.id !== id)];
    });
  }

  toggleSources() {
    const open = !this.sourcesOpen();
    this.sourcesOpen.set(open);
    if (this.wide()) this.storage.setPref('sourcesOpen', open);
  }
  closeSources() {
    this.sourcesOpen.set(false);
    if (this.wide()) this.storage.setPref('sourcesOpen', false);
  }

  onScroll(e: Event) {
    const el = e.target as HTMLElement;
    const gap = el.scrollHeight - el.scrollTop - el.clientHeight;
    this.pinned = gap < 120;
    this.awayFromBottom.set(gap > 400);
  }
  jumpLatest() {
    this.pinned = true;
    const el = this.scroller()?.nativeElement;
    el?.scrollTo({ top: el.scrollHeight, behavior: 'smooth' });
  }

  cite(msgId: string, n: number) {
    this.activeMsg.set(msgId);
    this.highlight.set(n);
    this.sourcesOpen.set(true);
  }
  showSources(msgId: string) {
    this.activeMsg.set(msgId);
    this.highlight.set(null);
    this.sourcesOpen.set(true);
  }
  stop() {
    this.abort?.abort();
  }

  /** Edit and send: forget this question and everything after it (here and in the server's memory), then ask the new text. */
  async editAndSend(msgId: string, text: string) {
    if (this.busy() || !text) return;
    const msgs = this.messages();
    const idx = msgs.findIndex((m) => m.id === msgId);
    if (idx < 0) return;
    const turns = msgs.slice(0, idx).filter((m) => m.role === 'user').length;
    try {
      await this.api.rewind(this.activeId(), turns);
    } catch { /* the server could not rewind: the answer may still see the later questions */ }
    this.messages.update((ms) => ms.slice(0, ms.findIndex((m) => m.id === msgId)));
    this.highlight.set(null);
    await this.ask(text);
  }

  async ask(typed: string, attachments: Attachment[] = []) {
    if (this.busy()) return;
    const text = typed || (attachments.length ? 'What does this image show, and what do our documents say about it?' : '');
    if (!text) return;
    const sessionId = this.activeId();
    const user: UIMessage = { id: uid(), role: 'user', content: typed, images: attachments.map((a) => a.thumb) };
    const asst: UIMessage = { id: uid(), role: 'assistant', content: '', streaming: true, steps: [] };
    this.messages.update((m) => [...m, user, asst]);
    this.activeMsg.set(asst.id);
    this.highlight.set(null);
    this.busy.set(true);
    this.pinned = true;
    this.touch(sessionId, typed || 'Image question');
    const update = (fn: (m: UIMessage) => UIMessage) => this.messages.update((ms) => ms.map((m) => (m.id === asst.id ? fn(m) : m)));
    const ctrl = new AbortController();
    this.abort = ctrl;
    const started = performance.now();
    try {
      await this.api.streamChat(
        { session_id: sessionId, message: text, filters: buildFilters(this.domain()), images: attachments.map((a) => a.full) },
        (ev) => {
          if (ev.type === 'status') update((m) => ({ ...m, steps: [...(m.steps ?? []), { step: ev.step, message: ev.message }] }));
          else if (ev.type === 'token') update((m) => ({ ...m, content: m.content + ev.text }));
          else if (ev.type === 'reset') update((m) => ({ ...m, content: '' }));
          else if (ev.type === 'final')
            update((m) => ({ ...m, content: ev.answer, sources: ev.sources, mode: ev.mode, intent: ev.intent, notices: ev.notices, timings: ev.timings, elapsedMs: performance.now() - started, streaming: false }));
          else if (ev.type === 'error') update((m) => ({ ...m, error: ev.message, streaming: false }));
        },
        ctrl.signal,
      );
    } catch (e) {
      const aborted = e instanceof DOMException && e.name === 'AbortError';
      update((m) => ({
        ...m,
        streaming: false,
        error: aborted ? undefined : `Could not reach the assistant: ${(e as Error).message}`,
        notices: aborted ? ['Generation stopped.'] : m.notices,
      }));
    } finally {
      update((m) => ({ ...m, streaming: false }));
      this.busy.set(false);
      this.abort = null;
      this.loadSessions(); // the server has stored this answer: refresh the list from it
    }
  }
}
