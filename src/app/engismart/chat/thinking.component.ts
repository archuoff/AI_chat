import { ChangeDetectionStrategy, Component, computed, input } from '@angular/core';
import { IconComponent } from '../ui/icon.component';

const STEPS = [
  { id: 'plan', label: 'Understanding your question' },
  { id: 'retrieve', label: 'Searching the knowledge base' },
  { id: 'rewrite', label: 'Refining the search' },
  { id: 'generate', label: 'Writing the answer' },
];

/** Live progress while an answer is being prepared: the current step pulses, finished steps tick off. */
@Component({
  selector: 'eng-thinking',
  imports: [IconComponent],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="t">
      @for (s of done(); track s.id) { <div class="done"><eng-icon name="check" [size]="13" [stroke]="3" /> {{ s.label }}</div> }
      <div class="now"><span class="dot"></span><span class="shim">{{ label() }}…</span></div>
    </div>`,
  styles: [`
    .t { display: flex; flex-direction: column; gap: 6px; padding: 4px 0; } .done { display: flex; align-items: center; gap: 8px; font-size: 13px; color: #4e4b66; opacity: 0.75; }
    .done eng-icon { color: #0b8f81; } .now { display: flex; align-items: center; gap: 10px; }
    .dot { width: 10px; height: 10px; border-radius: 50%; background: #0000b3; box-shadow: 0 0 0 0 rgba(107, 122, 232, 0.5); animation: ping 1.4s infinite; }
    @keyframes ping { 70% { box-shadow: 0 0 0 9px rgba(107, 122, 232, 0); } 100% { box-shadow: 0 0 0 0 rgba(107, 122, 232, 0); } }
    .shim { font-size: 14px; font-weight: 500; background: linear-gradient(90deg, #4e4b66 20%, #0000b3 50%, #4e4b66 80%); background-size: 200% 100%; -webkit-background-clip: text; background-clip: text; color: transparent; animation: shim 2s linear infinite; }
    @keyframes shim { to { background-position: -200% 0; } }`],
})
export class ThinkingComponent {
  readonly steps = input<{ step: string; message?: string }[]>([]);
  readonly seen = computed(() => this.steps().map((s) => s.step));
  readonly order = computed(() => STEPS.filter((s) => this.seen().some((x) => x === s.id || x.startsWith(`${s.id}.`))));
  readonly done = computed(() => this.order().slice(0, -1));
  readonly label = computed(() => this.steps().at(-1)?.message || 'Thinking');
}
