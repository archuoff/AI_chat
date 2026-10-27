import { ChangeDetectionStrategy, Component, computed, inject, OnInit, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ApiService } from '../core/api.service';
import { domainVisual } from '../core/domains';
import { cleanName, fileVisual } from '../core/format';
import type { DocumentInfo, Domain } from '../core/types';
import { FileBadgeComponent } from '../ui/file-badge.component';
import { IconComponent } from '../ui/icon.component';
import { DocDetailComponent } from './doc-detail.component';
import { LibraryDashboardComponent } from './library-dashboard.component';
import { UploadPanelComponent } from './upload-panel.component';

const plural = (n: number, word: string) => `${n} ${word}${n === 1 ? '' : 's'}`;
/** Something on this file needs a human look (not every processing note: only data that was not captured). */
export const needsReview = (d: DocumentInfo) => d.stats?.coverage_percent !== undefined && d.stats.coverage_percent < 99.9;

@Component({
  selector: 'eng-manage-page',
  imports: [FormsModule, IconComponent, FileBadgeComponent, DocDetailComponent, LibraryDashboardComponent, UploadPanelComponent],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './manage.page.html',
  styleUrl: './manage.page.scss',
})
export class ManagePage implements OnInit {
  private readonly api = inject(ApiService);
  readonly docs = signal<DocumentInfo[] | null>(null);
  readonly domains = signal<Domain[]>([]);
  readonly q = signal('');
  readonly domainFilter = signal<string | null>(null);
  readonly selectedId = signal<string | null>(null);
  readonly checked = signal<Set<string>>(new Set());
  readonly uploadOpen = signal(false);
  readonly moving = signal(false);
  readonly showReplaced = signal(false);
  readonly mobileDetail = signal(false);
  readonly loadError = signal<string | null>(null);

  readonly live = computed(() => (this.docs() ?? []).filter((d) => !d.superseded));
  readonly replacedCount = computed(() => (this.docs()?.length ?? 0) - this.live().length);
  readonly shown = computed(() => {
    const term = this.q().trim().toLowerCase();
    const f = this.domainFilter();
    return (this.showReplaced() ? (this.docs() ?? []) : this.live()).filter(
      (d) => (!f || (d.domain ?? 'unassigned') === f) && (!term || d.file_name.toLowerCase().includes(term)));
  });
  /** files grouped under their domain, in the registry's order */
  readonly groups = computed(() => {
    const order = [...this.domains().map((d) => d.id), 'unassigned'];
    const by = new Map<string, DocumentInfo[]>();
    for (const d of this.shown()) {
      const id = d.domain ?? 'unassigned';
      by.set(id, [...(by.get(id) ?? []), d]);
    }
    return [...by.entries()].sort(([a], [b]) => order.indexOf(a) - order.indexOf(b)).map(([id, ds]) => ({ id, ds }));
  });
  readonly emptyDomains = computed(() => (this.q().trim() || this.domainFilter() ? [] : this.domains().filter((d) => d.id !== 'unassigned' && !this.live().some((x) => x.domain === d.id))));
  readonly selected = computed(() => (this.docs() ?? []).find((d) => d.doc_id === this.selectedId()) ?? null);

  readonly emptySet = new Set<string>();
  readonly dv = domainVisual;
  readonly clean = cleanName;
  readonly ftype = (t: string) => fileVisual(t).label;
  readonly plural = plural;
  readonly needsReview = needsReview;
  readonly related = (id: string) => (this.docs() ?? []).find((d) => d.doc_id === id);

  ngOnInit() {
    void this.refresh();
  }

  async refresh(): Promise<void> {
    try {
      const [docs, domains] = await Promise.all([this.api.documents(), this.api.domains()]);
      this.docs.set(docs);
      this.domains.set(domains);
      this.loadError.set(null);
    } catch (e) {
      this.loadError.set((e as Error).message);
      this.docs.update((d) => d ?? []);
    }
  }

  open(id: string) {
    this.selectedId.set(id);
    if (typeof matchMedia === 'function' && !matchMedia('(min-width: 768px)').matches) this.mobileDetail.set(true);
  }
  toggle(id: string, on: boolean) {
    this.checked.update((cur) => {
      const next = new Set(cur);
      if (on) next.add(id); else next.delete(id);
      return next;
    });
  }
  async bulkMove(domain: string) {
    this.moving.set(true);
    try {
      await this.api.bulkDomain([...this.checked()], domain);
      this.checked.set(new Set());
      await this.refresh();
    } catch (e) {
      this.loadError.set((e as Error).message);
    } finally {
      this.moving.set(false);
    }
  }
  async deleted() {
    this.selectedId.set(null);
    this.mobileDetail.set(false);
    await this.refresh();
  }
  onCheck(id: string, ev: Event) {
    this.toggle(id, (ev.target as HTMLInputElement).checked);
  }
}
