import { ChangeDetectionStrategy, Component, input, output } from '@angular/core';
import type { ExcelPreview } from '../core/types';

@Component({
  selector: 'eng-sheet-tabs',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `<div class="t eng-scroll">@for (s of preview().sheets; track s.name) { <button type="button" [class.on]="s.name === preview().sheet.name" (click)="sheetChange.emit(s.name)">{{ s.name }}</button> }</div>`,
  styles: [`
    .t { display: flex; gap: 4px; overflow-x: auto; padding-bottom: 4px; } button { flex: none; border: 0; background: transparent; border-radius: 8px; padding: 6px 12px; font: inherit; font-size: 12.5px; font-weight: 500; white-space: nowrap; color: var(--eng-slate); cursor: pointer; }
    button:hover { background: rgba(255, 255, 255, 0.7); color: var(--eng-navy); } button.on { background: #fff; font-weight: 700; color: var(--eng-navy); box-shadow: 0 0 0 1px var(--eng-line), var(--eng-shadow); }`],
})
export class SheetTabsComponent {
  readonly preview = input.required<ExcelPreview>();
  readonly sheetChange = output<string>();
}
