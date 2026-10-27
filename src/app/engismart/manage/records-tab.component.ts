import { ChangeDetectionStrategy, Component, computed, input, output, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import type { ExcelPreview } from '../core/types';
import { IconComponent } from '../ui/icon.component';
import { SheetTabsComponent } from './sheet-tabs.component';

@Component({
  selector: 'eng-records-tab',
  imports: [FormsModule, IconComponent, SheetTabsComponent],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    @if (!preview()) { <div class="spin"><eng-icon name="loader" [size]="22" [spin]="true" /></div> }
    @else {
      <div class="r">
        <div class="bar"><div class="st"><eng-sheet-tabs [preview]="preview()!" (sheetChange)="sheetChange.emit($event)" /></div>
          <div class="s"><eng-icon name="search" [size]="15" /><input class="eng-input" [ngModel]="q()" (ngModelChange)="q.set($event)" placeholder="Filter records…" aria-label="Filter records" /></div></div>
        <p class="hint">Each row is stored as one record, exactly as the assistant reads and quotes it.</p>
        <div class="list eng-scroll">
          @if (!tables().length) { <p class="none">No table records on this sheet.</p> }
          @for (x of tables(); track x.t.id) {
            <section class="eng-card">
              <div class="th"><b>{{ x.t.title || preview()!.sheet.name }}</b><span class="rg">{{ x.t.range }}</span><span class="cnt">{{ term() ? x.rows.length + ' of ' + x.total : x.total }} records</span></div>
              <div class="tw eng-scroll"><table>
                <thead><tr><th class="row">Row</th>@if (x.hasSection) { <th>Section</th> }@for (n of x.names; track n) { <th>{{ n }}</th> }</tr></thead>
                <tbody>@for (r of x.rows; track r.row) { <tr><td class="row">{{ r.row }}</td>@if (x.hasSection) { <td class="sec">{{ r.section.at(-1) }}</td> }@for (n of x.names; track n) { <td [title]="cell(r.fields[n])"><div class="cl">{{ cell(r.fields[n]) }}</div></td> }</tr> }</tbody>
              </table></div>
            </section>
          }
        </div>
      </div>
    }`,
  styles: [`
    :host { display: block; height: 100%; min-height: 0; } .spin { display: flex; height: 256px; align-items: center; justify-content: center; color: var(--eng-primary); } .r { display: flex; flex-direction: column; gap: 12px; height: 100%; min-height: 0; }
    .bar { display: flex; flex-wrap: wrap; align-items: center; gap: 12px; } .st { flex: 1; min-width: 0; } .s { position: relative; width: 256px; } .s eng-icon { position: absolute; left: 12px; top: 50%; transform: translateY(-50%); color: rgba(78, 75, 102, 0.6); } .s input { padding-left: 34px; }
    .hint { margin: 0; font-size: 12.5px; color: var(--eng-slate); } .list { flex: 1; min-height: 0; display: flex; flex-direction: column; gap: 16px; } .none { padding: 40px 0; text-align: center; font-size: 13px; color: var(--eng-slate); }
    .th { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; padding: 12px 16px; border-bottom: 1px solid var(--eng-line); } .th b { font-size: 13.5px; color: var(--eng-navy); } .rg { font-size: 11.5px; color: rgba(78, 75, 102, 0.7); } .cnt { margin-left: auto; font-size: 12px; color: var(--eng-slate); }
    .tw { max-height: 60vh; overflow: auto; } table { width: max-content; min-width: 100%; border-collapse: separate; border-spacing: 0; text-align: left; font-size: 12.5px; } th { position: sticky; top: 0; z-index: 1; background: #f4f5fb; padding: 8px 12px; font-size: 11.5px; font-weight: 700; color: var(--eng-navy); border-bottom: 1px solid var(--eng-line); min-width: 140px; max-width: 260px; }
    th.row, td.row { position: sticky; left: 0; min-width: 0; color: rgba(78, 75, 102, 0.7); } th.row { z-index: 2; color: var(--eng-slate); } td.row { background: #fff; } td { padding: 8px 12px; vertical-align: top; border-bottom: 1px solid var(--eng-line); max-width: 260px; } td.sec { color: #0b6f64; } tr:hover td { background: rgba(238, 240, 248, 0.6); } tr:hover td.row { background: #f0f2fa; }
    .cl { display: -webkit-box; -webkit-line-clamp: 4; line-clamp: 4; -webkit-box-orient: vertical; overflow: hidden; white-space: pre-line; overflow-wrap: anywhere; }`],
})
export class RecordsTabComponent {
  readonly preview = input<ExcelPreview | null>(null);
  readonly sheetChange = output<string>();
  readonly q = signal('');
  readonly term = computed(() => this.q().trim().toLowerCase());
  readonly cell = (v: unknown) => (v != null ? String(v) : '');
  readonly tables = computed(() => {
    const p = this.preview();
    if (!p) return [];
    return p.sheet.tables.filter((t) => (p.sheet.records[t.id] ?? []).length > 0).map((t) => {
      const rows = p.sheet.records[t.id];
      const names = t.columns.map((c) => c.name).filter((n) => rows.some((r) => n in r.fields));
      const hasSection = rows.some((r) => r.section.length > 0);
      const shown = this.term() ? rows.filter((r) => JSON.stringify(r.fields).toLowerCase().includes(this.term())) : rows;
      return { t, names, hasSection, rows: shown, total: rows.length };
    });
  });
}
