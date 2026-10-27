import { ChangeDetectionStrategy, Component, computed, HostListener, input, output, signal } from '@angular/core';
import type { CellStatus, ParseOptions } from '../core/types';
import type { ExcelPreview } from '../core/types';
import { IconComponent } from '../ui/icon.component';
import { colLetter, STATUS_META, STATUS_ORDER } from './excel';
import { PictureCardComponent, SheetCardComponent, TableCardComponent } from './sheet-cards.component';
import { SheetGridComponent } from './sheet-grid.component';
import { SheetTabsComponent } from './sheet-tabs.component';

@Component({
  selector: 'eng-sheet-preview',
  imports: [IconComponent, SheetGridComponent, SheetTabsComponent, SheetCardComponent, TableCardComponent, PictureCardComponent],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './sheet-preview.component.html',
  styleUrl: './sheet-preview.component.scss',
})
export class SheetPreviewComponent {
  readonly preview = input<ExcelPreview | null>(null);
  readonly loading = input(false);
  readonly error = input<string | null>(null);
  readonly draft = input<ParseOptions>({});
  readonly draftChange = output<ParseOptions>();
  readonly sheetChange = output<string>();

  readonly activeTable = signal<string | null>(null);
  readonly selected = signal<string | null>(null);
  readonly expanded = signal(false);
  readonly showPictures = signal(true);
  readonly pictureId = signal<string | null>(null);
  readonly meta = STATUS_META;

  readonly counts = computed(() => {
    const c: Partial<Record<CellStatus, number>> = {};
    for (const r of this.preview()?.sheet.rows ?? []) for (const cell of r.cells) c[cell.s] = (c[cell.s] ?? 0) + 1;
    return c;
  });
  readonly legend = computed(() => STATUS_ORDER.filter((s) => this.counts()[s]));
  readonly pictures = computed(() => this.preview()?.sheet.pictures ?? []);
  readonly picture = computed(() => this.pictures().find((p) => p.id === this.pictureId()) ?? null);
  readonly selCell = computed(() => {
    const sel = this.selected(), p = this.preview();
    if (!sel || !p) return null;
    return p.sheet.rows.flatMap((r) => r.cells.map((c) => ({ ...c, r: r.r }))).find((c) => `${colLetter(c.c)}${c.r}` === sel) ?? null;
  });
  readonly sheetIncluded = computed(() => !this.draft().sheets?.[this.preview()?.sheet.name ?? '']?.skip);

  @HostListener('window:keydown', ['$event'])
  onKey(e: KeyboardEvent) { if (e.key === 'Escape' && this.expanded()) this.expanded.set(false); }

  changeSheet(name: string) {
    this.selected.set(null);
    this.activeTable.set(null);
    this.pictureId.set(null);
    this.sheetChange.emit(name);
  }
  setSheetIncluded(on: boolean) {
    const name = this.preview()!.sheet.name;
    const sheets = { ...(this.draft().sheets ?? {}) };
    if (!on) sheets[name] = { skip: true }; else delete sheets[name];
    this.draftChange.emit({ ...this.draft(), sheets });
  }
  setTable(id: string, patch: { header_rows?: number | null; skip?: boolean }) {
    const tables = { ...(this.draft().tables ?? {}) };
    const next: { header_rows?: number | null; skip?: boolean } = { ...(tables[id] ?? {}), ...patch };
    if (next.header_rows === null || next.header_rows === undefined) delete next.header_rows;
    if (!next.skip) delete next.skip;
    if (Object.keys(next).length) tables[id] = next; else delete tables[id];
    this.draftChange.emit({ ...this.draft(), tables });
  }
}
