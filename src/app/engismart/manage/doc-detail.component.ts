import { ChangeDetectionStrategy, Component, computed, effect, HostListener, inject, input, output, signal, untracked } from '@angular/core';
import { ApiService } from '../core/api.service';
import { domainVisual } from '../core/domains';
import { bytes, cleanName, fileVisual, timeAgo } from '../core/format';
import type { DocumentInfo, Domain, DomainSuggestion, ExcelPreview, ParseOptions } from '../core/types';
import { FileBadgeComponent } from '../ui/file-badge.component';
import { IconComponent } from '../ui/icon.component';
import { ChunksTabComponent } from './chunks-tab.component';
import { normalize, optionsEqual } from './excel';
import { ImagesTabComponent } from './images-tab.component';
import { OverviewTabComponent } from './overview-tab.component';
import { RecordsTabComponent } from './records-tab.component';
import { SheetPreviewComponent } from './sheet-preview.component';

type Tab = 'overview' | 'preview' | 'records' | 'images' | 'chunks';
type Busy = null | 'apply' | 'reprocess' | 'delete' | 'domain' | 'suggest' | 'access' | 'restore';

@Component({
  selector: 'eng-doc-detail',
  imports: [IconComponent, FileBadgeComponent, OverviewTabComponent, SheetPreviewComponent, RecordsTabComponent, ImagesTabComponent, ChunksTabComponent],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './doc-detail.component.html',
  styleUrl: './doc-detail.component.scss',
})
export class DocDetailComponent {
  private readonly api = inject(ApiService);
  readonly doc = input.required<DocumentInfo>();
  readonly domains = input<Domain[]>([]);
  /** other documents of the library, to name the version this one replaced / was replaced by */
  readonly related = input.required<(id: string) => DocumentInfo | undefined>();
  readonly openDoc = output<string>();
  readonly changed = output<void>();
  readonly deleted = output<void>();
  readonly closed = output<void>();

  readonly tab = signal<Tab>('overview');
  readonly sheet = signal<string | undefined>(undefined);
  readonly preview = signal<ExcelPreview | null>(null);
  readonly previewLoading = signal(false);
  readonly previewError = signal<string | null>(null);
  readonly draft = signal<ParseOptions>({});
  readonly busy = signal<Busy>(null);
  readonly toast = signal<{ kind: 'ok' | 'err'; text: string } | null>(null);
  readonly suggestion = signal<DomainSuggestion | null>(null);
  readonly menu = signal<null | 'domain' | 'more'>(null);

  readonly isExcel = computed(() => ['xlsx', 'xlsm'].includes(this.doc().file_type));
  readonly dv = computed(() => domainVisual(this.doc().domain));
  readonly pending = computed(() => !optionsEqual(this.draft(), this.doc().parse_options));
  readonly pendingCount = computed(() => Object.keys(normalize(this.draft()).tables ?? {}).length + Object.keys(normalize(this.draft()).sheets ?? {}).length);
  readonly tabs = computed(() => {
    const d = this.doc();
    return ([
      { id: 'overview', label: 'Overview', show: true, count: undefined },
      { id: 'preview', label: 'Sheet preview', show: this.isExcel(), count: undefined },
      { id: 'records', label: 'Records', show: this.isExcel(), count: d.records },
      { id: 'images', label: 'Pictures', show: (d.images?.total ?? 0) > 0, count: d.images?.total },
      { id: 'chunks', label: 'Search chunks', show: true, count: d.chunks },
    ] as { id: Tab; label: string; show: boolean; count?: number }[]).filter((t) => t.show);
  });
  readonly info = computed(() => `${fileVisual(this.doc().file_type).label} · ${bytes(this.doc().size_bytes)} · updated ${timeAgo(this.doc().ingested_at)}`);
  readonly replacedBy = computed(() => (this.doc().replaced_by ? this.related()(this.doc().replaced_by!) : undefined));
  readonly replacesDoc = computed(() => (this.doc().replaces ? this.related()(this.doc().replaces!) : undefined));
  readonly replacedAgo = computed(() => (this.doc().replaced_at ? ` ${timeAgo(this.doc().replaced_at!)}` : ''));
  readonly clean = cleanName;
  readonly dvOf = domainVisual;
  readonly pct = (n: number) => Math.round(n * 100);

  constructor() {
    // a new document was selected: reset everything
    effect(() => {
      this.doc().doc_id;
      untracked(() => {
        this.tab.set('overview');
        this.sheet.set(undefined);
        this.preview.set(null);
        this.previewError.set(null);
        this.suggestion.set(null);
        this.toast.set(null);
        this.menu.set(null);
      });
    });
    effect(() => this.draft.set(this.doc().parse_options ?? {}));
    effect(() => {
      const tab = this.tab();
      this.sheet(); this.doc().doc_id; this.doc().ingested_at;
      if (this.isExcel() && (tab === 'preview' || tab === 'records')) untracked(() => this.loadPreview());
    });
    effect((onCleanup) => {
      if (!this.toast()) return;
      const t = setTimeout(() => this.toast.set(null), 5000);
      onCleanup(() => clearTimeout(t));
    });
  }

  @HostListener('window:keydown', ['$event'])
  onKey(e: KeyboardEvent) {
    if (e.key !== 'Escape' || this.menu() || document.querySelector('.eng-modal-open')) return;
    if ((e.target as HTMLElement)?.closest?.('input, textarea, select')) return;
    this.closed.emit();
  }

  private loadPreview() {
    this.previewLoading.set(true);
    this.previewError.set(null);
    const id = this.doc().doc_id;
    this.api.excelPreview(id, this.sheet()).then((p) => this.doc().doc_id === id && this.preview.set(p))
      .catch((e: Error) => this.previewError.set(e.message)).finally(() => this.previewLoading.set(false));
  }

  async run(kind: Exclude<Busy, null>, fn: () => Promise<string | void>) {
    this.busy.set(kind);
    try {
      const msg = await fn();
      if (msg) this.toast.set({ kind: 'ok', text: msg });
    } catch (e) {
      this.toast.set({ kind: 'err', text: (e as Error).message });
    } finally {
      this.busy.set(null);
    }
  }

  setDomain(domain: string) {
    this.menu.set(null);
    return this.run('domain', async () => {
      await this.api.setDomain(this.doc().doc_id, domain);
      this.changed.emit();
      this.suggestion.set(null);
      return `Moved to ${domainVisual(domain).label}`;
    });
  }
  suggest() {
    this.menu.set(null);
    return this.run('suggest', async () => { this.suggestion.set(await this.api.suggestDomain(this.doc().doc_id)); });
  }
  toggleAccess() {
    return this.run('access', async () => {
      const next = !this.doc().confidential;
      await this.api.setConfidential(this.doc().doc_id, next);
      this.changed.emit();
      return next ? 'Marked confidential: only super users and developers can see it' : 'Now visible to everyone with access to this domain';
    });
  }
  reprocess() {
    this.menu.set(null);
    return this.run('reprocess', async () => {
      const r = await this.api.reprocess(this.doc().doc_id);
      this.changed.emit();
      return `Re-processed in ${r.seconds}s`;
    });
  }
  remove() {
    this.menu.set(null);
    if (!confirm(`Remove "${cleanName(this.doc().file_name)}" from the knowledge base? The assistant will no longer use it.`)) return;
    return this.run('delete', async () => {
      await this.api.deleteDocument(this.doc().doc_id);
      this.deleted.emit();
    });
  }
  restore() {
    return this.run('restore', async () => {
      await this.api.restoreDocument(this.doc().doc_id);
      this.changed.emit();
      return 'Restored: the assistant can use this version again';
    });
  }
  apply() {
    return this.run('apply', async () => {
      const r = await this.api.saveParseOptions(this.doc().doc_id, normalize(this.draft()));
      this.changed.emit();
      return `Changes applied: ${r.records ?? 0} records stored (${r.seconds}s)`;
    });
  }
  discard() { this.draft.set(this.doc().parse_options ?? {}); }
  openSheet(s: string) { this.sheet.set(s); this.tab.set('preview'); }
}
