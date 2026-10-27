import { ChangeDetectionStrategy, Component, computed, input, output } from '@angular/core';
import type { ExcelPicture, ExcelPreview } from '../core/types';
import { AuthImageComponent } from '../ui/auth-image.component';
import { colLetter, rangeBounds, STATUS_META } from './excel';

type Sheet = ExcelPreview['sheet'];
type Cell = Sheet['rows'][number]['cells'][number];
type Line = { kind: 'row'; r: number; cells: GridCell[] } | { kind: 'gap'; from: number; to: number };
type GridCell = { c: number; key: string; address: string; cell?: Cell; rs?: number; cs?: number; pics: ExcelPicture[]; label?: string };

const key = (r: number, c: number) => `${r}:${c}`;

/** The original worksheet, merged cells included, coloured by what the parser did with each cell. */
@Component({
  selector: 'eng-sheet-grid',
  imports: [AuthImageComponent],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './sheet-grid.component.html',
  styleUrl: './sheet-grid.component.scss',
})
export class SheetGridComponent {
  readonly sheet = input.required<Sheet>();
  readonly activeTable = input<string | null>(null);
  readonly selected = input<string | null>(null);
  readonly pictures = input<ExcelPicture[]>([]);
  readonly showPictures = input(false);
  readonly activePicture = input<string | null>(null);
  readonly select = output<string | null>();
  readonly pick = output<string | null>();
  readonly letter = colLetter;
  readonly cols = computed(() => Array.from({ length: this.sheet().shown_cols }, (_, i) => i + 1));

  private readonly active = computed(() => {
    const id = this.activeTable();
    const tab = id ? this.sheet().tables.find((x) => x.id === id) : null;
    return tab ? rangeBounds(tab.range) : null;
  });

  readonly lines = computed<Line[]>(() => {
    const sheet = this.sheet();
    const cells = new Map<string, Cell>();
    const usedRows = new Set<number>();
    for (const row of sheet.rows) {
      for (const cell of row.cells) cells.set(key(row.r, cell.c), cell);
      usedRows.add(row.r);
    }
    const spans = new Map<string, { rs: number; cs: number }>();
    const covered = new Set<string>();
    for (const m of sheet.merges) {
      spans.set(key(m.r0, m.c0), { rs: m.r1 - m.r0 + 1, cs: m.c1 - m.c0 + 1 });
      for (let r = m.r0; r <= m.r1; r++) {
        usedRows.add(r);
        for (let c = m.c0; c <= m.c1; c++) if (r !== m.r0 || c !== m.c0) covered.add(key(r, c));
      }
    }
    const picAt = new Map<string, ExcelPicture[]>();
    for (const p of this.pictures()) {
      const k = key(p.r, p.c);
      picAt.set(k, [...(picAt.get(k) ?? []), p]);
      for (let r = p.r; r <= p.r1; r++) usedRows.add(r); // a picture on an otherwise empty row keeps its row
    }
    const show = this.showPictures();
    const rowCells = (r: number): GridCell[] => {
      const out: GridCell[] = [];
      for (const c of this.cols()) {
        const k = key(r, c);
        if (covered.has(k)) continue;
        const cell = cells.get(k);
        const pics = show ? picAt.get(k) ?? [] : [];
        out.push({ c, key: k, address: `${colLetter(c)}${r}`, cell, rs: spans.get(k)?.rs, cs: spans.get(k)?.cs, pics,
                   label: cell && !(pics.length && cell.v.startsWith('[picture')) ? cell.v : undefined });
      }
      return out;
    };
    // collapse long runs of empty rows (and never split a merged block)
    const lines: Line[] = [];
    let r = 1;
    while (r <= sheet.shown_rows) {
      if (usedRows.has(r)) { lines.push({ kind: 'row', r, cells: rowCells(r) }); r++; continue; }
      let end = r;
      while (end + 1 <= sheet.shown_rows && !usedRows.has(end + 1)) end++;
      if (end - r + 1 >= 3) lines.push({ kind: 'gap', from: r, to: end });
      else for (let x = r; x <= end; x++) lines.push({ kind: 'row', r: x, cells: rowCells(x) });
      r = end + 1;
    }
    return lines;
  });

  dim(r: number, c: number): boolean {
    const a = this.active();
    return !!a && !(r >= a.r0 && r <= a.r1 && c >= a.c0 && c <= a.c1);
  }
  meta = (c?: Cell) => (c ? STATUS_META[c.s] : null);
  cls = (c?: Cell) => (c ? `st-${c.s}` : '');
  click(g: GridCell) {
    this.select.emit(g.cell ? (this.selected() === g.address ? null : g.address) : null);
  }
  clickPic(ev: Event, p: ExcelPicture) {
    ev.stopPropagation();
    this.pick.emit(this.activePicture() === p.id ? null : p.id);
  }
}
