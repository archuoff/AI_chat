import { ChangeDetectionStrategy, Component, computed, effect, ElementRef, input, output, signal, viewChild } from '@angular/core';
import { FormsModule } from '@angular/forms';
import type { UIMessage } from '../core/types';
import { IconComponent } from '../ui/icon.component';
import { MarkdownComponent } from '../ui/markdown.component';
import { ThinkingComponent } from './thinking.component';

const INTENT_LABEL: Record<string, string> = { lookup: 'Fact lookup', comparison: 'Comparison', list: 'List', explanation: 'Explanation', exact_id: 'Exact ID', chitchat: 'Conversation' };
const STEP_LABEL: Record<string, string> = {
  plan: 'Understand question', 'retrieve.embed': 'Embed question', 'retrieve.search': 'Search index', 'retrieve.rerank': 'Rank evidence',
  'retrieve.judge': 'Check relevance', rewrite: 'Rephrase search', generate: 'Write answer',
};

@Component({
  selector: 'eng-message',
  imports: [FormsModule, IconComponent, MarkdownComponent, ThinkingComponent],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './message.component.html',
  styleUrl: './message.component.scss',
})
export class MessageComponent {
  readonly msg = input.required<UIMessage>();
  readonly active = input(false);
  /** edit and send is offered only when true (not while an answer is being written) */
  readonly canEdit = input(false);
  readonly cite = output<number>();
  readonly showSources = output<void>();
  readonly edited = output<string>();
  readonly editing = signal(false);
  readonly draft = signal('');
  readonly box = viewChild<ElementRef<HTMLTextAreaElement>>('box');
  readonly copied = signal(false);
  readonly zoom = signal<string | null>(null);

  readonly sources = computed(() => this.msg().sources ?? []);
  readonly citedCount = computed(() => this.sources().filter((s) => s.cited).length);
  readonly done = computed(() => !this.msg().streaming && this.msg().intent !== 'chitchat');
  readonly meta = computed(() => {
    const m = this.msg();
    return [
      m.intent && m.intent !== 'chitchat' ? INTENT_LABEL[m.intent] ?? m.intent : null,
      this.done() && m.mode ? (m.mode === 'azure-openai' ? 'Azure OpenAI' : 'Extracted from sources') : null,
    ].filter(Boolean).join(' · ');
  });
  readonly timingTitle = computed(() => {
    const t = this.msg().timings;
    if (!t) return 'Response time';
    return Object.entries(STEP_LABEL).filter(([k]) => t[k] !== undefined).map(([k, label]) => `${label}: ${(t[k] / 1000).toFixed(1)} s`).join('\n');
  });
  readonly seconds = computed(() => ((this.msg().elapsedMs ?? 0) / 1000).toFixed(1));

  constructor() {
    effect(() => {
      this.draft();
      const el = this.box()?.nativeElement;
      if (!el) return;
      el.style.height = '0px';
      el.style.height = `${Math.min(el.scrollHeight, 240)}px`;
    });
    effect(() => {
      const el = this.box()?.nativeElement;
      if (el && this.editing()) {
        el.focus();
        el.setSelectionRange(el.value.length, el.value.length);
      }
    });
  }

  startEdit() {
    this.draft.set(this.msg().content);
    this.editing.set(true);
  }
  send() {
    const text = this.draft().trim();
    if (!text) return;
    this.editing.set(false);
    this.edited.emit(text);
  }
  onKey(e: KeyboardEvent) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      this.send();
    } else if (e.key === 'Escape') this.editing.set(false);
  }

  async copy() {
    try {
      await navigator.clipboard.writeText(this.msg().content);
      this.copied.set(true);
      setTimeout(() => this.copied.set(false), 1400);
    } catch { /* clipboard blocked */ }
  }
}
