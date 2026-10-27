import { ChangeDetectionStrategy, Component, effect, ElementRef, inject, input, output, signal } from '@angular/core';
import { cleanName, locationLabel } from '../core/format';
import type { Source } from '../core/types';
import { AuthImageComponent } from '../ui/auth-image.component';
import { FileBadgeComponent } from '../ui/file-badge.component';
import { IconComponent } from '../ui/icon.component';

@Component({
  selector: 'eng-source-card',
  imports: [AuthImageComponent, FileBadgeComponent, IconComponent],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    @let s = source();
    <div class="card" [class.hl]="highlighted()">
      <div class="top">
        <div class="bw"><eng-file-badge [type]="s.file_type" /><span class="n" [class.cited]="s.cited">{{ s.n }}</span></div>
        <div class="tx">
          <div class="fn" [title]="s.file_name">{{ clean(s.file_name) }}</div>
          <div class="loc"><eng-icon name="pin" [size]="12" />{{ where(s) }}</div>
          @if (s.title) { <div class="ttl">{{ s.title }}</div> }
        </div>
      </div>
      <div class="bar"><div class="track"><div class="fill" [style.width.%]="pct(s)"></div></div><span>{{ pct(s) }}%</span></div>
      @if (s.image_id) {
        <button type="button" class="pic" (click)="open.set(!open())" [title]="open() ? 'Smaller' : 'Larger'">
          <eng-auth-image [id]="s.image_id" [thumb]="!open()" [alt]="'Picture from ' + clean(s.file_name)" [class.big]="open()" />
        </button>
      }
      <button type="button" class="snip" (click)="open.set(!open())" [title]="open() ? 'Collapse' : 'Expand'"><span [class.clamp]="!open()">{{ s.snippet }}</span></button>
    </div>`,
  styles: [`
    :host { display: block; } .card { border: 1px solid var(--eng-line); background: #fff; border-radius: 16px; padding: 14px; transition: border-color 0.15s, box-shadow 0.15s; }
    .card:hover { border-color: rgba(107, 122, 232, 0.5); box-shadow: var(--eng-shadow); } .card.hl { border-color: var(--eng-primary); box-shadow: 0 0 0 3px rgba(0, 0, 179, 0.12); }
    .top { display: flex; gap: 12px; align-items: flex-start; } .bw { position: relative; }
    .n { position: absolute; top: -6px; right: -6px; min-width: 18px; height: 18px; padding: 0 4px; border-radius: 99px; display: flex; align-items: center; justify-content: center; font-size: 10px; font-weight: 700; background: var(--eng-line); color: var(--eng-slate); box-shadow: 0 0 0 2px #fff; }
    .n.cited { background: var(--eng-primary); color: #fff; } .tx { min-width: 0; flex: 1; }
    .fn { font-size: 13.5px; font-weight: 700; color: var(--eng-navy); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
    .loc { margin-top: 2px; display: flex; align-items: center; gap: 4px; font-size: 12px; color: var(--eng-slate); } .loc eng-icon { color: var(--eng-periwinkle); }
    .ttl { margin-top: 4px; font-size: 12.5px; font-weight: 500; color: rgba(26, 29, 51, 0.8); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
    .bar { margin-top: 12px; display: flex; align-items: center; gap: 8px; font-size: 11px; font-weight: 700; color: var(--eng-slate); } .track { flex: 1; height: 6px; border-radius: 99px; background: var(--eng-mist); overflow: hidden; }
    .fill { height: 100%; border-radius: 99px; background: linear-gradient(90deg, var(--eng-primary), var(--eng-teal)); transition: width 0.6s ease-out; } .bar span { width: 36px; text-align: right; }
    .pic { display: block; width: 100%; margin-top: 10px; padding: 0; overflow: hidden; border-radius: 10px; border: 1px solid var(--eng-line); background: rgba(238, 240, 248, 0.5); cursor: pointer; }
    .pic eng-auth-image { height: 144px; } .pic eng-auth-image.big { height: auto; max-height: 384px; min-height: 120px; }
    .snip { display: block; width: 100%; margin-top: 10px; padding: 8px 12px; border: 0; border-radius: 10px; background: rgba(238, 240, 248, 0.7); text-align: left; font: inherit; font-size: 12.5px; line-height: 1.55; color: rgba(26, 29, 51, 0.85); cursor: pointer; }
    .snip:hover { background: var(--eng-mist); } .snip span { display: block; white-space: pre-line; overflow-wrap: anywhere; } .clamp { display: -webkit-box !important; -webkit-line-clamp: 3; line-clamp: 3; -webkit-box-orient: vertical; overflow: hidden; }`],
})
export class SourceCardComponent {
  private readonly el = inject<ElementRef<HTMLElement>>(ElementRef);
  readonly source = input.required<Source>();
  readonly highlighted = input(false);
  readonly open = signal(false);
  clean = cleanName;
  where = (s: Source) => locationLabel(s.location) || 'Document';
  pct = (s: Source) => Math.round(Math.min(1, Math.max(0, s.score)) * 100);
  constructor() {
    effect(() => {
      if (this.highlighted()) {
        this.el.nativeElement.scrollIntoView?.({ behavior: 'smooth', block: 'nearest' });
        this.open.set(true);
      }
    });
  }
}

@Component({
  selector: 'eng-sources-panel',
  imports: [SourceCardComponent, IconComponent],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="p">
      <div class="h">
        <eng-icon name="book" [size]="17" /><h2>Sources</h2><span class="count">{{ sources().length }}</span>
        <button type="button" class="eng-icon-btn x" (click)="closed.emit()" aria-label="Close sources" title="Close sources"><eng-icon name="x" [size]="17" /></button>
      </div>
      <div class="list eng-scroll">
        @if (!sources().length) {
          <div class="empty"><div class="ei"><eng-icon name="book" [size]="24" /></div><p class="et">Evidence appears here</p><p>Every answer is traced back to the exact sheet, row, page or slide it came from.</p></div>
        } @else {
          @if (cited().length) { <div class="eng-label">Cited in answer</div> }
          @for (s of cited(); track s.n) { <eng-source-card [source]="s" [highlighted]="highlight() === s.n" /> }
          @if (others().length) { <div class="eng-label gap">Also retrieved</div> }
          @for (s of others(); track s.n) { <eng-source-card [source]="s" [highlighted]="highlight() === s.n" /> }
        }
      </div>
    </div>`,
  styles: [`
    .p { display: flex; flex-direction: column; height: 100%; } .h { display: flex; align-items: center; gap: 8px; padding: 14px 18px; border-bottom: 1px solid var(--eng-line); } .h eng-icon { color: var(--eng-primary); }
    h2 { margin: 0; font-size: 15px; font-weight: 800; color: var(--eng-navy); } .count { border-radius: 99px; background: var(--eng-mist); padding: 2px 8px; font-size: 11.5px; font-weight: 700; color: var(--eng-slate); } .x { margin-left: auto; }
    .list { flex: 1; padding: 16px; display: flex; flex-direction: column; gap: 12px; } .gap { padding-top: 8px; }
    .empty { margin: auto; text-align: center; padding: 0 24px; color: var(--eng-slate); font-size: 12.5px; line-height: 1.6; } .ei { margin: 0 auto 14px; width: 64px; height: 64px; border-radius: 16px; border: 1px solid var(--eng-line); background: #fff; display: flex; align-items: center; justify-content: center; color: var(--eng-periwinkle); }
    .et { margin: 0 0 4px; font-size: 14px; font-weight: 700; color: var(--eng-navy); }`],
})
export class SourcesPanelComponent {
  readonly sources = input<Source[]>([]);
  readonly highlight = input<number | null>(null);
  readonly closed = output<void>();
  cited = () => this.sources().filter((s) => s.cited);
  others = () => this.sources().filter((s) => !s.cited);
}
