import { ChangeDetectionStrategy, Component, computed, input, output } from '@angular/core';
import type { Domain } from '../core/types';
import { IconComponent } from '../ui/icon.component';
import { blocker, chosenDoc, partialWarning, UploadItem } from './upload.types';

/** Per file: what the system found in the library, and the SME's choice (new document / update of ...). */
@Component({
  selector: 'eng-upload-decision',
  imports: [IconComponent],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './upload-decision.component.html',
  styleUrl: './upload-decision.component.scss',
})
export class UploadDecisionComponent {
  readonly item = input.required<UploadItem>();
  readonly domains = input<Domain[]>([]);
  readonly change = output<Partial<UploadItem>>();
  readonly c = computed(() => this.item().check!);
  readonly live = computed(() => this.c().exact.filter((e) => !e.superseded));
  readonly hidden = computed(() => this.c().exact.filter((e) => e.superseded));
  readonly partial = computed(() => (this.item().intent === 'update' ? partialWarning(chosenDoc(this.item())?.sig_size, this.c().size) : null));
  readonly stop = computed(() => blocker(this.item()));
  readonly suggested = computed(() => new Set(this.c().suggestions.map((s) => s.doc_id)));
  readonly others = computed(() => this.c().others.filter((o) => !this.suggested().has(o.doc_id)));
  name = (id: string) => this.domains().find((d) => d.id === id)?.name ?? id;
  why = (reasons: string[]) => reasons.filter((x) => x !== 'same domain').join(' · ') || 'similar';
}
