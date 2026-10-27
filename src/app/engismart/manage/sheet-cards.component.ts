import { ChangeDetectionStrategy, Component, computed, input, output, signal } from '@angular/core';
import type { ExcelPicture, ExcelPreview, TableInfo } from '../core/types';
import { AuthImageComponent } from '../ui/auth-image.component';
import { IconComponent } from '../ui/icon.component';
import { colLetter } from './excel';

type Patch = { header_rows?: number | null; skip?: boolean };

@Component({
  selector: 'eng-toggle',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `<button type="button" class="t" [class.on]="on()" role="switch" [attr.aria-checked]="on()" (click)="$event.preventDefault(); change.emit(!on())"><span></span></button>`,
  styles: [`.t { position: relative; width: 36px; height: 20px; border: 0; border-radius: 99px; background: var(--eng-line); cursor: pointer; padding: 0; transition: background 0.15s; } .t.on { background: var(--eng-primary); }
    span { position: absolute; top: 2px; left: 2px; width: 16px; height: 16px; border-radius: 50%; background: #fff; box-shadow: 0 1px 2px rgba(0, 0, 0, 0.3); transition: left 0.15s; } .on span { left: 18px; }`],
})
export class ToggleComponent {
  readonly on = input(false);
  readonly change = output<boolean>();
}

const PICTURE_STATUS: Record<string, { label: string; cls: string }> = {
  described: { label: 'Described', cls: 'green' }, waiting: { label: 'Waiting for description', cls: 'amber' }, skipped: { label: 'Skipped', cls: '' },
  failed: { label: 'Failed', cls: 'red' }, unsupported: { label: 'Unreadable', cls: 'red' },
};

/** One picture of the sheet: the large image, what happened to it, its description and the text sent to the vision model. */
@Component({
  selector: 'eng-picture-card',
  imports: [AuthImageComponent, IconComponent],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    @let p = picture();
    <div class="pc">
      <div class="h"><span class="addr">{{ address() }}</span><span class="w">{{ p.placement === 'in_cell' ? 'Picture in the cell' : 'Picture on the sheet' }}</span><button type="button" class="eng-icon-btn x" (click)="closed.emit()" aria-label="Close picture details"><eng-icon name="x" [size]="14" /></button></div>
      <eng-auth-image class="img" [id]="p.id" [thumb]="false" [alt]="'Picture in ' + address()" />
      <div class="st"><span class="eng-chip" [class]="'eng-chip ' + status().cls">{{ status().label }}</span>@if (p.width > 0) { <span class="dim">{{ p.width }}×{{ p.height }} px</span> }</div>
      @if (p.reason) { <p class="rs">{{ p.reason }}</p> }
      @if (p.description) { <div class="ds"><b>Description</b><p>{{ p.description }}</p></div> }
      @if (p.context) { <details><summary>Text sent to the vision model</summary><p class="ctx">{{ p.context }}</p></details> }
    </div>`,
  styles: [`
    .pc { border: 1px solid rgba(0, 0, 179, 0.4); background: #fff; border-radius: 12px; padding: 12px; box-shadow: 0 0 0 3px rgba(0, 0, 179, 0.06); } .h { display: flex; align-items: center; gap: 8px; } .addr { background: var(--eng-navy); color: #fff; font-size: 12px; font-weight: 800; padding: 2px 8px; border-radius: 8px; } .w { font-size: 12px; color: var(--eng-slate); } .x { margin-left: auto; width: 26px; height: 26px; }
    .img { display: block; margin-top: 10px; max-height: 256px; min-height: 80px; border-radius: 8px; overflow: hidden; background: var(--eng-mist); } .st { margin-top: 10px; display: flex; flex-wrap: wrap; align-items: center; gap: 8px; } .dim { font-size: 11px; color: rgba(78, 75, 102, 0.7); }
    .rs { margin: 6px 0 0; font-size: 12px; color: var(--eng-slate); } .ds { margin-top: 8px; } .ds b { font-size: 11.5px; color: var(--eng-navy); } .ds p { margin: 2px 0 0; font-size: 12.5px; white-space: pre-line; overflow-wrap: anywhere; }
    details { margin-top: 8px; } summary { cursor: pointer; font-size: 11.5px; font-weight: 700; color: var(--eng-slate); } .ctx { margin: 4px 0 0; max-height: 160px; overflow-y: auto; border-radius: 8px; background: var(--eng-mist); padding: 8px; font-size: 11.5px; white-space: pre-line; color: var(--eng-slate); overflow-wrap: anywhere; }`],
})
export class PictureCardComponent {
  readonly picture = input.required<ExcelPicture>();
  readonly closed = output<void>();
  readonly status = computed(() => PICTURE_STATUS[this.picture().status] ?? { label: this.picture().status, cls: '' });
  readonly address = computed(() => `${colLetter(this.picture().c)}${this.picture().r}`);
}

@Component({
  selector: 'eng-sheet-card',
  imports: [IconComponent, ToggleComponent],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    @let c = sheet().coverage;
    <div class="sc eng-card">
      <div class="top"><eng-icon [name]="ok() ? 'check' : 'alert'" [size]="18" [class]="ok() ? 'good' : 'warn'" />
        <div><div class="t">{{ ok() ? 'All data captured' : c.percent + '% of the data captured' }}</div>
          <div class="s">{{ sheet().record_count }} record{{ sheet().record_count === 1 ? '' : 's' }} stored@if ((sheet().in_cell_pictures ?? 0) > 0) { · {{ sheet().in_cell_pictures }} picture{{ sheet().in_cell_pictures === 1 ? '' : 's' }} in cells }@if (c.ignored_count > 0) { · {{ c.ignored_count }} error cell{{ c.ignored_count === 1 ? '' : 's' }} skipped }</div></div></div>
      @if (c.missed.length) {
        <div class="miss"><b>Not captured: click a cell to inspect it</b><div class="chips">@for (m of c.missed.slice(0, 12); track m.cell) { <button type="button" [title]="m.value" (click)="pick.emit(m.cell)">{{ m.cell }}</button> }</div></div>
      }
      <label class="inc"><span><span class="l">Include in knowledge base</span>@if (!included()) { <span class="n">Nothing from this sheet will be stored</span> }</span><eng-toggle [on]="included()" (change)="includedChange.emit($event)" /></label>
    </div>`,
  styles: [`
    .top { display: flex; gap: 10px; padding: 16px; } .top eng-icon { margin-top: 1px; } .good { color: var(--eng-teal); } .warn { color: #e8a33d; } .t { font-size: 13.5px; font-weight: 700; color: var(--eng-navy); } .s { margin-top: 2px; font-size: 12px; line-height: 1.35; color: var(--eng-slate); }
    .miss { margin: 0 16px 16px; border-radius: 8px; background: #fdf0ea; padding: 10px; } .miss b { font-size: 12px; color: #8a3510; } .chips { margin-top: 6px; display: flex; flex-wrap: wrap; gap: 4px; } .chips button { border: 0; border-radius: 6px; background: #fff; padding: 2px 6px; font: inherit; font-size: 11px; font-weight: 800; color: #8a3510; box-shadow: 0 0 0 1px rgba(194, 65, 12, 0.3); cursor: pointer; }
    .inc { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 12px 16px; border-top: 1px solid var(--eng-line); cursor: pointer; user-select: none; } .l { display: block; font-size: 13px; font-weight: 500; } .n { display: block; font-size: 11.5px; color: #a8471a; }`],
})
export class SheetCardComponent {
  readonly sheet = input.required<ExcelPreview['sheet']>();
  readonly included = input(true);
  readonly pick = output<string>();
  readonly includedChange = output<boolean>();
  readonly ok = computed(() => this.sheet().coverage.percent >= 99.9);
}

@Component({
  selector: 'eng-table-card',
  imports: [IconComponent],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    @let t = table();
    <div class="tc eng-card" [class.act]="active()" [class.skip]="skip()" (mouseenter)="hover.emit(true)" (mouseleave)="hover.emit(false)">
      <div class="h"><b>{{ isText() ? 'Text block' : 'Table ' + index() }}</b><span class="rg">{{ t.range }}</span>
        @if (t.overridden) { <span class="eng-chip amber">Corrected</span> }@if (skip()) { <span class="eng-chip red">Excluded</span> }</div>
      @if (t.title) { <div class="tt">{{ t.title }}</div> }
      @if (isText()) { <p class="d">Title or notes, stored as text ({{ t.preamble_rows.length }} line{{ t.preamble_rows.length === 1 ? '' : 's' }}).</p> }
      @else {
        <p class="d">{{ t.records }} record{{ t.records === 1 ? '' : 's' }} · {{ t.columns.length }} column{{ t.columns.length === 1 ? '' : 's' }}@if (t.section_rows.length > 0) { · {{ t.section_rows.length }} section{{ t.section_rows.length === 1 ? '' : 's' }} }</p>
        <div class="hr"><div><div class="hl">Header rows</div><div class="hs">@if (pending()) { <b>changed from {{ applied() }}</b> } @else { detected {{ t.header_rows_detected }} }</div></div>
          <div class="step"><button type="button" (click)="change.emit({ header_rows: max0(value() - 1) })" aria-label="Fewer header rows"><eng-icon name="minus" [size]="13" /></button><span class="v">{{ value() }}</span>
            <button type="button" (click)="change.emit({ header_rows: min4(value() + 1) })" aria-label="More header rows"><eng-icon name="plus" [size]="13" /></button>
            @if (t.overridden || draft()?.header_rows !== undefined) { <button type="button" class="rs" (click)="change.emit({ header_rows: null })" title="Back to auto-detect"><eng-icon name="undo" [size]="13" /></button> }</div></div>
        <button type="button" class="sc" (click)="open.set(!open())">{{ open() ? 'Hide columns' : 'Show columns' }}<eng-icon [name]="open() ? 'chevron-down' : 'chevron-right'" [size]="14" /></button>
        @if (open()) { <div class="cols">@for (c of t.columns; track c.col) { <div class="col"><span class="cc">{{ c.col }}</span><span class="cn" [class.gen]="c.name.startsWith('Column ')">{{ c.name }}</span><span class="cf">{{ c.filled }}</span></div> }</div> }
      }
      <div class="ft"><button type="button" [class.inc]="skip()" (click)="change.emit({ skip: !skip() })"><eng-icon [name]="skip() ? 'eye' : 'x'" [size]="13" /> {{ skip() ? 'Include table' : 'Exclude table' }}</button></div>
    </div>`,
  styles: [`
    .tc { padding: 16px; transition: border-color 0.15s; } .tc.act { border-color: rgba(0, 0, 179, 0.6); box-shadow: 0 0 0 3px rgba(0, 0, 179, 0.08); } .tc.skip { opacity: 0.7; } .h { display: flex; align-items: center; gap: 8px; } .h b { font-size: 13.5px; color: var(--eng-navy); } .rg { font-size: 11.5px; color: rgba(78, 75, 102, 0.7); }
    .tt { margin-top: 2px; font-size: 12.5px; color: var(--eng-slate); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; } .d { margin: 6px 0 0; font-size: 12px; color: var(--eng-slate); }
    .hr { margin-top: 12px; padding-top: 12px; border-top: 1px solid var(--eng-line); display: flex; align-items: center; justify-content: space-between; gap: 8px; } .hl { font-size: 12.5px; font-weight: 500; } .hs { font-size: 11px; color: var(--eng-slate); } .hs b { color: #9a5a06; }
    .step { display: flex; align-items: center; gap: 4px; } .step button { width: 28px; height: 28px; border: 0; border-radius: 8px; background: #fff; box-shadow: 0 0 0 1px var(--eng-line); cursor: pointer; display: inline-flex; align-items: center; justify-content: center; color: var(--eng-ink); } .step button:hover { background: var(--eng-mist); } .step .rs { margin-left: 4px; box-shadow: none; width: 26px; } .v { width: 28px; text-align: center; font-size: 15px; font-weight: 800; color: var(--eng-navy); }
    .sc { margin-top: 12px; display: flex; width: 100%; align-items: center; justify-content: space-between; border: 0; background: transparent; padding: 0; font: inherit; font-size: 12px; font-weight: 500; color: var(--eng-slate); cursor: pointer; } .cols { margin-top: 8px; max-height: 224px; overflow-y: auto; display: flex; flex-direction: column; gap: 4px; } .col { display: flex; gap: 8px; font-size: 12px; } .cc { width: 24px; flex: none; font-weight: 800; color: var(--eng-slate); } .cn { flex: 1; min-width: 0; overflow-wrap: anywhere; } .cn.gen { color: var(--eng-ember); font-style: italic; } .cf { color: rgba(78, 75, 102, 0.7); }
    .ft { margin-top: 8px; display: flex; justify-content: flex-end; } .ft button { display: inline-flex; align-items: center; gap: 6px; border: 0; background: transparent; border-radius: 6px; padding: 4px 8px; font: inherit; font-size: 12px; font-weight: 500; color: var(--eng-slate); cursor: pointer; } .ft button:hover { background: #fdf0ea; color: #8a3510; } .ft .inc { color: var(--eng-primary); } .ft .inc:hover { background: rgba(0, 0, 179, 0.06); color: var(--eng-primary); }`],
})
export class TableCardComponent {
  readonly table = input.required<TableInfo>();
  readonly index = input(1);
  readonly draft = input<Patch | undefined>(undefined);
  readonly active = input(false);
  readonly hover = output<boolean>();
  readonly change = output<Patch>();
  readonly open = signal(false);
  readonly applied = computed(() => this.table().header_rows.length);
  readonly value = computed(() => this.draft()?.header_rows ?? this.applied());
  readonly pending = computed(() => this.draft()?.header_rows !== undefined && this.draft()?.header_rows !== this.applied());
  readonly skip = computed(() => this.draft()?.skip ?? false);
  readonly isText = computed(() => this.table().kind === 'text' && !this.table().skipped);
  readonly max0 = (n: number) => Math.max(0, n);
  readonly min4 = (n: number) => Math.min(4, n);
}
