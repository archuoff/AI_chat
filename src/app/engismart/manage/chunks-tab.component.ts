import { ChangeDetectionStrategy, Component, computed, effect, inject, input, signal, untracked } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ApiService } from '../core/api.service';
import { locationLabel } from '../core/format';
import type { ChunkInfo, DocumentInfo } from '../core/types';
import { IconComponent } from '../ui/icon.component';

@Component({
  selector: 'eng-chunks-tab',
  imports: [FormsModule, IconComponent],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="c">
      <div class="bar">
        <p>The searchable pieces stored in the search index ({{ doc().chunks }}). Each is embedded together with its context line ({{ doc().embedding_model ?? 'embedding model' }}).</p>
        <div class="s"><eng-icon name="search" [size]="15" /><input class="eng-input" [ngModel]="q()" (ngModelChange)="q.set($event)" placeholder="Filter chunks…" aria-label="Filter chunks" /></div>
      </div>
      <div class="list eng-scroll">
        @if (!chunks() && !error()) { <div class="spin"><eng-icon name="loader" [size]="22" [spin]="true" /></div> }
        @if (error(); as e) { <p class="err">{{ e }}</p> }
        @for (c of shown(); track c.id) {
          <div class="ch eng-card">
            <div class="meta"><span class="idx">#{{ c.chunk_index }}</span><span class="kind" [class.rec]="c.kind === 'record'">{{ c.kind === 'record' ? 'Table record' : 'Text' }}</span><span class="loc">{{ where(c.location) }}</span></div>
            <div class="ctx" [title]="c.context">{{ c.context }}</div>
            @if (c.kind === 'record' && c.fields) {
              <table class="kv"><tbody>@for (f of entries(c.fields); track f[0]) { <tr><td>{{ f[0] }}</td><td>{{ f[1] }}</td></tr> }</tbody></table>
            } @else { <p class="tx">{{ c.text }}</p> }
          </div>
        }
      </div>
    </div>`,
  styles: [`
    :host { display: block; height: 100%; min-height: 0; } .c { display: flex; flex-direction: column; gap: 12px; height: 100%; min-height: 0; } .bar { display: flex; flex-wrap: wrap; align-items: center; gap: 12px; } .bar p { flex: 1; min-width: 200px; margin: 0; font-size: 12.5px; color: var(--eng-slate); }
    .s { position: relative; width: 256px; } .s eng-icon { position: absolute; left: 12px; top: 50%; transform: translateY(-50%); color: rgba(78, 75, 102, 0.6); } .s input { padding-left: 34px; }
    .list { flex: 1; min-height: 0; display: flex; flex-direction: column; gap: 12px; } .spin { display: flex; justify-content: center; padding: 64px 0; color: var(--eng-primary); } .err { color: var(--eng-ember); font-size: 13px; }
    .ch { padding: 16px; } .meta { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; } .idx { background: var(--eng-navy); color: #fff; font-size: 10.5px; font-weight: 800; padding: 2px 6px; border-radius: 6px; }
    .kind { font-size: 11px; font-weight: 700; padding: 2px 8px; border-radius: 6px; background: rgba(107, 122, 232, 0.15); color: var(--eng-primary); } .kind.rec { background: #d7f5f1; color: #0b6f64; } .loc { font-size: 12px; color: var(--eng-slate); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
    .ctx { margin-top: 8px; font-size: 11.5px; color: rgba(78, 75, 102, 0.8); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
    .kv { margin-top: 10px; width: 100%; table-layout: fixed; border-collapse: collapse; border: 1px solid var(--eng-line); font-size: 12.5px; overflow-wrap: anywhere; } .kv td { padding: 6px 12px; vertical-align: top; border-top: 1px solid var(--eng-line); white-space: pre-line; } .kv tr:first-child td { border-top: 0; } .kv td:first-child { width: 36%; background: rgba(238, 240, 248, 0.7); font-weight: 700; color: var(--eng-navy); }
    .tx { margin: 10px 0 0; font-size: 13px; line-height: 1.6; white-space: pre-line; overflow-wrap: anywhere; color: rgba(26, 29, 51, 0.9); }`],
})
export class ChunksTabComponent {
  private readonly api = inject(ApiService);
  readonly doc = input.required<DocumentInfo>();
  readonly chunks = signal<ChunkInfo[] | null>(null);
  readonly error = signal<string | null>(null);
  readonly q = signal('');
  readonly shown = computed(() => {
    const t = this.q().trim().toLowerCase();
    return (this.chunks() ?? []).filter((c) => !t || c.text.toLowerCase().includes(t) || c.context.toLowerCase().includes(t));
  });
  readonly where = locationLabel;
  readonly entries = (o: Record<string, unknown>) => Object.entries(o).map(([k, v]) => [k, String(v)] as [string, string]);

  constructor() {
    effect(() => {
      const id = this.doc().doc_id;
      this.doc().ingested_at;
      untracked(() => {
        this.chunks.set(null);
        this.error.set(null);
        this.api.chunks(id, 2000).then((c) => this.chunks.set(c)).catch((e: Error) => this.error.set(e.message));
      });
    });
  }
}
