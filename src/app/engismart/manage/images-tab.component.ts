import { ChangeDetectionStrategy, Component, computed, effect, inject, input, OnDestroy, output, signal, untracked } from '@angular/core';
import { ApiService } from '../core/api.service';
import type { DescribeJob, DocImage, DocImages, DocumentInfo, ImageStatus } from '../core/types';
import { AuthImageComponent } from '../ui/auth-image.component';
import { IconComponent } from '../ui/icon.component';

export const pictureWhere = (loc: DocImage['location']): string =>
  loc.slide ? `Slide ${loc.slide}` : loc.page ? `Page ${loc.page}` : loc.sheet ? `${loc.sheet}${loc.cell ? ` · ${loc.cell}` : ''}` : loc.section || 'Document';

const STATUS: Record<ImageStatus, { label: string; color: string }> = {
  waiting: { label: 'Waiting', color: '#e8a33d' }, described: { label: 'Described', color: '#0b8f81' }, skipped: { label: 'Skipped', color: '#dfe2ee' },
  unsupported: { label: 'Unreadable', color: '#9a9db3' }, failed: { label: 'Failed', color: '#c2410c' },
};
const column = (img: DocImage) => /^Column: (.+)$/m.exec(img.context)?.[1] ?? '';
/** Card label: inside a sheet group the sheet name is the heading, so show cell + column. */
const cardLabel = (img: DocImage) => (img.location.sheet ? [img.location.cell, column(img)].filter(Boolean).join(' · ') || img.location.sheet : pictureWhere(img.location));
const tokens = (n: number) => (n >= 1000 ? `${Math.round(n / 1000)}k` : String(n));

@Component({
  selector: 'eng-images-tab',
  imports: [IconComponent, AuthImageComponent],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './images-tab.component.html',
  styleUrl: './images-tab.component.scss',
})
export class ImagesTabComponent implements OnDestroy {
  private readonly api = inject(ApiService);
  readonly doc = input.required<DocumentInfo>();
  readonly changed = output<void>();
  readonly data = signal<DocImages | null>(null);
  readonly error = signal<string | null>(null);
  readonly filter = signal<'all' | ImageStatus>('all');
  readonly open = signal<DocImage | null>(null);
  readonly job = signal<DescribeJob | null>(null);
  readonly busy = signal(false);
  private timer: ReturnType<typeof setInterval> | null = null;

  readonly where = pictureWhere;
  readonly label = cardLabel;
  readonly tk = tokens;
  readonly st = STATUS;
  readonly running = computed(() => this.job()?.state === 'running');
  readonly counts = computed(() => this.data()?.counts);
  readonly pending = computed(() => (this.counts() ? this.counts()!.waiting + this.counts()!.failed : 0));
  readonly filters = computed(() => (['all', 'waiting', 'described', 'skipped', 'unsupported', 'failed'] as const).filter((f) => f === 'all' || (this.counts()?.[f] ?? 0) > 0));
  readonly count = (f: 'all' | ImageStatus) => (f === 'all' ? this.counts()?.total : this.counts()?.[f]) ?? 0;
  readonly shown = computed(() => (this.data()?.images ?? []).filter((i) => this.filter() === 'all' || i.status === this.filter()));
  /** Excel: one group per sheet; other files: a single group */
  readonly groups = computed(() => {
    const m = new Map<string, DocImage[]>();
    for (const img of this.shown()) m.set(img.location.sheet ?? '', [...(m.get(img.location.sheet ?? '') ?? []), img]);
    return [...m.entries()].map(([sheet, imgs]) => ({ sheet, imgs }));
  });
  readonly estTokens = computed(() => (this.data() ? this.data()!.estimate.input_tokens + this.data()!.estimate.output_tokens : 0));
  readonly jobTokens = computed(() => (this.job()?.input_tokens ?? 0) + (this.job()?.output_tokens ?? 0));
  readonly jobPct = computed(() => ((this.job()?.done ?? 0) / Math.max(this.job()?.total ?? 1, 1)) * 100);

  constructor() {
    effect(() => {
      this.doc().doc_id;
      untracked(() => this.load());
    });
    this.api.describeJob().then((j) => this.job.set(j)).catch(() => undefined);
    effect(() => {
      if (this.running() && !this.timer) {
        this.timer = setInterval(() => this.api.describeJob().then((j) => {
          this.job.set(j);
          if (j.state !== 'running') { this.load(); this.changed.emit(); }
        }), 1500);
      }
      if (!this.running() && this.timer) { clearInterval(this.timer); this.timer = null; }
    });
  }
  ngOnDestroy() { if (this.timer) clearInterval(this.timer); }

  load() { this.api.docImages(this.doc().doc_id).then((d) => this.data.set(d), (e: Error) => this.error.set(e.message)); }

  async describe() {
    const d = this.data()!;
    const est = d.estimate;
    const cost = est.cost !== null ? ` (about ${est.cost.toFixed(2)})` : '';
    if (!confirm(`Describe ${this.pending()} picture${this.pending() === 1 ? '' : 's'} with ${d.vision.deployment}?\n\nEstimated ${tokens(this.estTokens())} tokens${cost}.`)) return;
    this.busy.set(true);
    try { this.job.set(await this.api.describeImages({ doc_ids: [this.doc().doc_id] })); }
    catch (e) { this.error.set((e as Error).message); }
    finally { this.busy.set(false); }
  }
  async stop() { this.job.set(await this.api.cancelDescribe()); }
  async setIncluded(img: DocImage, included: boolean) {
    this.open.set(await this.api.setImageIncluded(img.id, included));
    this.load();
    this.changed.emit();
  }
}
