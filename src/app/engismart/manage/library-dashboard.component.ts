import { ChangeDetectionStrategy, Component, computed, effect, inject, input, OnDestroy, output, signal } from '@angular/core';
import { ApiService } from '../core/api.service';
import { domainVisual } from '../core/domains';
import { cleanName, fileVisual, timeAgo } from '../core/format';
import type { DocumentInfo, Domain, ImagesSummary } from '../core/types';
import { FileBadgeComponent } from '../ui/file-badge.component';
import { IconComponent } from '../ui/icon.component';

// one colour per file family for the type bar
const TYPE_COLOR: Record<string, string> = { Excel: '#12a596', PowerPoint: '#f2a039', Word: '#698cf7', PDF: '#d75d27', CSV: '#0b6f64' };
const fmt = (n: number) => n.toLocaleString('en-GB');
const isExcel = (d: DocumentInfo) => d.file_type === 'xlsx' || d.file_type === 'xlsm';
const needsReview = (d: DocumentInfo) => d.stats?.coverage_percent !== undefined && d.stats.coverage_percent < 99.9;
export const ktokens = (n: number) => (n >= 1000 ? `${Math.round(n / 1000)}k` : String(n));

@Component({
  selector: 'eng-library-dashboard',
  imports: [IconComponent, FileBadgeComponent],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './library-dashboard.component.html',
  styleUrl: './library-dashboard.component.scss',
})
export class LibraryDashboardComponent implements OnDestroy {
  private readonly api = inject(ApiService);
  readonly docs = input.required<DocumentInfo[]>();
  readonly domains = input.required<Domain[]>();
  readonly openDoc = output<string>();
  readonly domainPick = output<string>();
  readonly add = output<void>();
  readonly pics = signal<ImagesSummary | null>(null);
  readonly picBusy = signal(false);
  private timer: ReturnType<typeof setInterval> | null = null;

  readonly clean = cleanName;
  readonly ago = timeAgo;
  readonly num = fmt;
  readonly kt = ktokens;
  readonly typeColor = (label: string) => TYPE_COLOR[label] ?? '#9aa0b4';

  readonly s = computed(() => {
    const docs = this.docs(), domains = this.domains();
    const records = docs.reduce((a, d) => a + d.records, 0);
    const chunks = docs.reduce((a, d) => a + d.chunks, 0);
    const excel = docs.filter((d) => isExcel(d) && d.stats?.coverage_percent !== undefined);
    const coverage = excel.length ? excel.reduce((a, d) => a + (d.stats.coverage_percent ?? 0), 0) / excel.length : null;
    const attention = docs.filter(needsReview);
    const confidential = docs.filter((d) => d.confidential).length;
    const types = new Map<string, number>();
    for (const d of docs) types.set(fileVisual(d.file_type).label, (types.get(fileVisual(d.file_type).label) ?? 0) + 1);
    const recent = [...docs].sort((a, b) => +new Date(b.ingested_at) - +new Date(a.ingested_at)).slice(0, 5);
    const byDomain = domains
      .filter((d) => d.id !== 'unassigned' || docs.some((x) => (x.domain ?? 'unassigned') === 'unassigned'))
      .map((d) => {
        const ds = docs.filter((x) => (x.domain ?? 'unassigned') === d.id);
        return { ...d, files: ds.length, chunks: ds.reduce((a, x) => a + x.chunks, 0), color: domainVisual(d.id).color };
      });
    const maxChunks = Math.max(1, ...byDomain.map((d) => d.chunks));
    return { records, chunks, coverage, attention, confidential, types: [...types.entries()].sort((a, b) => b[1] - a[1]), recent, byDomain, maxChunks };
  });
  readonly kpis = computed(() => {
    const s = this.s();
    return [
      { label: 'Documents', value: fmt(this.docs().length), note: s.confidential ? `${s.confidential} confidential` : 'none confidential' },
      { label: 'Records', value: fmt(s.records), note: 'rows from tables' },
      { label: 'Search chunks', value: fmt(s.chunks), note: 'what the assistant searches' },
      { label: 'Data captured', value: s.coverage === null ? '–' : `${Math.round(s.coverage * 10) / 10}%`, note: 'average across Excel files' },
    ];
  });
  readonly pending = computed(() => (this.pics() ? this.pics()!.counts.waiting + this.pics()!.counts.failed : 0));

  constructor() {
    effect(() => {
      this.docs();
      this.loadPics();
    });
    effect(() => {
      const running = this.pics()?.job.state === 'running';
      if (running && !this.timer) this.timer = setInterval(() => this.loadPics(), 2000);
      if (!running && this.timer) { clearInterval(this.timer); this.timer = null; }
    });
  }
  ngOnDestroy() { if (this.timer) clearInterval(this.timer); }

  private loadPics() { this.api.imagesSummary().then((p) => this.pics.set(p)).catch(() => undefined); }

  async describeAll() {
    const p = this.pics();
    if (!p) return;
    const est = p.estimate;
    const cost = est.cost !== null ? ` (about ${est.cost.toFixed(2)})` : '';
    if (!confirm(`Describe all ${this.pending()} waiting pictures with ${p.vision.deployment}?\n\nEstimated ${ktokens(est.input_tokens + est.output_tokens)} tokens${cost}.`)) return;
    this.picBusy.set(true);
    try {
      await this.api.describeImages({});
      this.pics.set(await this.api.imagesSummary());
    } catch (e) {
      alert((e as Error).message);
    } finally {
      this.picBusy.set(false);
    }
  }
}
