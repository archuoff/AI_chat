import { ChangeDetectionStrategy, Component, computed, effect, ElementRef, inject, input, output, signal, viewChild } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ApiService } from '../core/api.service';
import { domainVisual } from '../core/domains';
import { Attachment, imageFiles, MAX_ATTACHMENTS, prepareImage } from '../core/images';
import { DomainIconComponent } from '../ui/domain-icon.component';
import { IconComponent } from '../ui/icon.component';

/** 'all' = every domain this user may query (the server enforces the user's allowed domains) */
export const buildFilters = (domain: string): Record<string, unknown> | null => (domain !== 'all' ? { domain } : null);

@Component({
  selector: 'eng-composer',
  imports: [FormsModule, IconComponent, DomainIconComponent],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './composer.component.html',
  styleUrl: './composer.component.scss',
})
export class ComposerComponent {
  private readonly api = inject(ApiService);
  readonly busy = input(false);
  readonly domain = input('all');
  readonly domainOptions = input<string[]>(['all']);
  readonly domainChange = output<string>();
  readonly send = output<{ text: string; images: Attachment[] }>();
  readonly stop = output<void>();

  readonly text = signal('');
  readonly images = signal<Attachment[]>([]);
  readonly preparing = signal(0);
  readonly dragging = signal(false);
  readonly error = signal<string | null>(null);
  readonly menu = signal(false);
  readonly max = MAX_ATTACHMENTS;
  readonly waiting = computed(() => Array.from({ length: this.preparing() }));
  readonly ta = viewChild<ElementRef<HTMLTextAreaElement>>('ta');
  readonly fileInput = viewChild<ElementRef<HTMLInputElement>>('files');
  readonly dv = domainVisual;
  readonly canSend = computed(() => (this.text().trim().length > 0 || this.images().length > 0) && this.preparing() === 0 && !this.busy());
  readonly placeholder = computed(() => (this.images().length ? 'Ask about the image… (or just send it)' : this.domain() === 'all' ? '' : `Ask the ${domainVisual(this.domain()).label} knowledge base…`));

  constructor() {
    effect(() => {
      this.text();
      const el = this.ta()?.nativeElement;
      if (!el) return;
      el.style.height = '0px';
      el.style.height = `${Math.min(el.scrollHeight, 180)}px`;
      el.style.overflowY = el.scrollHeight > 180 ? 'auto' : 'hidden';
    });
  }

  private flash(msg: string) {
    this.error.set(msg);
    setTimeout(() => this.error() === msg && this.error.set(null), 4000);
  }

  async addFiles(files: File[]) {
    if (!files.length) return;
    const room = MAX_ATTACHMENTS - this.images().length;
    if (room <= 0) return this.flash(`You can attach up to ${MAX_ATTACHMENTS} images`);
    if (files.length > room) this.flash(`Only ${room} more image${room === 1 ? '' : 's'} can be attached`);
    this.api.warmup();
    const take = files.slice(0, room);
    this.preparing.update((n) => n + take.length);
    for (const f of take) {
      try {
        const a = await prepareImage(f);
        this.images.update((cur) => (cur.length < MAX_ATTACHMENTS ? [...cur, a] : cur));
      } catch (e) {
        this.flash((e as Error).message);
      } finally {
        this.preparing.update((n) => n - 1);
      }
    }
    this.ta()?.nativeElement.focus();
  }

  submit() {
    if (!this.canSend()) return;
    this.send.emit({ text: this.text().trim(), images: this.images() });
    this.text.set('');
    this.images.set([]);
  }

  onKey(e: KeyboardEvent) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      this.submit();
    }
  }
  onPaste(e: ClipboardEvent) {
    const files = imageFiles(e.clipboardData?.files);
    if (files.length) {
      e.preventDefault();
      void this.addFiles(files);
    }
  }
  onDragOver(e: DragEvent) {
    if (Array.from(e.dataTransfer?.items ?? []).some((i) => i.kind === 'file')) {
      e.preventDefault();
      this.dragging.set(true);
    }
  }
  onDragLeave(e: DragEvent) {
    if (!(e.currentTarget as HTMLElement).contains(e.relatedTarget as Node)) this.dragging.set(false);
  }
  onDrop(e: DragEvent) {
    e.preventDefault();
    this.dragging.set(false);
    void this.addFiles(imageFiles(e.dataTransfer?.files));
  }
  pickFiles(e: Event) {
    const input = e.target as HTMLInputElement;
    void this.addFiles(imageFiles(input.files));
    input.value = '';
  }
  remove(id: string) {
    this.images.update((cur) => cur.filter((x) => x.id !== id));
  }
  choose(d: string) {
    this.domainChange.emit(d);
    this.menu.set(false);
  }
  typed(v: string) {
    this.text.set(v);
    this.api.warmup();
  }
  warm() {
    this.api.warmup();
  }
}
