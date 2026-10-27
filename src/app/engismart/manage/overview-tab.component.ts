import { ChangeDetectionStrategy, Component, computed, input, output } from '@angular/core';
import type { DocumentInfo } from '../core/types';
import { IconComponent } from '../ui/icon.component';

const complete = (p: number) => p >= 99.9;

@Component({
  selector: 'eng-overview-tab',
  imports: [IconComponent],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './overview-tab.component.html',
  styleUrl: './overview-tab.component.scss',
})
export class OverviewTabComponent {
  readonly doc = input.required<DocumentInfo>();
  readonly openSheet = output<string>();
  readonly complete = complete;

  readonly isExcel = computed(() => ['xlsx', 'xlsm'].includes(this.doc().file_type));
  readonly sheets = computed(() => Object.entries(this.doc().stats.sheets ?? {}));
  readonly coverage = computed(() => this.doc().stats.coverage_percent);
  readonly toReview = computed(() => this.sheets().filter(([, s]) => !s.skipped && !complete(s.coverage.percent)).length);
  readonly ok = computed(() => this.coverage() === undefined || complete(this.coverage()!));
  readonly corrections = computed(() => {
    const o = this.doc().parse_options;
    return [
      ...Object.entries(o?.sheets ?? {}).filter(([, v]) => v.skip).map(([s]) => `Sheet "${s}" excluded`),
      ...Object.entries(o?.tables ?? {}).flatMap(([id, v]) => [
        ...(v.header_rows !== undefined && v.header_rows !== null ? [`${id}: ${v.header_rows} header row${v.header_rows === 1 ? '' : 's'}`] : []),
        ...(v.skip ? [`${id}: excluded`] : []),
      ]),
    ];
  });
  readonly stats = computed((): [string, string | number][] => {
    const d = this.doc();
    return this.isExcel()
      ? [['Sheets', this.sheets().length], ['Records', d.records], ['Search chunks', d.chunks], ['Captured', this.coverage() !== undefined ? `${this.coverage()}%` : '–']]
      : [[d.stats.pages ? 'Pages' : d.stats.slides ? 'Slides' : 'Text blocks', d.stats.pages ?? d.stats.slides ?? d.text_blocks], ['Text blocks', d.text_blocks], ['Table records', d.records], ['Search chunks', d.chunks]];
  });
  readonly meta = computed(() => Object.entries(this.doc().meta ?? {}).map(([k, v]) => ({ k: k.replace(/_/g, ' '), v: Array.isArray(v) ? v.join(', ') : String(v) })));
}
