import { ChangeDetectionStrategy, Component, computed, inject, input, output } from '@angular/core';
import { ApiService } from '../core/api.service';
import { IconComponent } from '../ui/icon.component';

// one pool across domains; only those in the user's allowed domains are shown
const SUGGESTIONS = [
  { q: 'Compare CCB weight across vehicles', tag: 'Benchmarking', domain: 'benchmarking', icon: 'table' },
  { q: 'What causes decoupling ring failures?', tag: 'FMEA', domain: 'adas', icon: 'shield' },
  { q: 'What is the minimum bond flange for the carbon fiber bonnet?', tag: 'Design guideline', domain: 'eds', icon: 'slides' },
  { q: 'What material is the BMW X5 cross car beam made of?', tag: 'Benchmarking', domain: 'benchmarking', icon: 'sheet' },
  { q: 'List the ultrasonic sensors and their package zones', tag: 'ADAS design rule', domain: 'adas', icon: 'table' },
  { q: 'What is the minimum detachment force for the sensor holder?', tag: 'ADAS design rule', domain: 'adas', icon: 'shield' },
  { q: 'What is the frunk volume of the BMW i3?', tag: 'Design guideline', domain: 'eds', icon: 'slides' },
  { q: 'How do I raise a PR AIMS?', tag: 'Lead engineering', domain: 'lead-engineering', icon: 'sheet' },
];

@Component({
  selector: 'eng-welcome',
  imports: [IconComponent],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './welcome.component.html',
  styleUrl: './welcome.component.scss',
})
export class WelcomeComponent {
  private readonly api = inject(ApiService);
  readonly domains = input<string[]>([]);
  readonly ask = output<string>();
  readonly shown = computed(() => {
    const allowed = new Set(this.domains());
    const picks = SUGGESTIONS.filter((s) => allowed.has(s.domain));
    const seen = new Set<string>(); // a balanced first four: one per domain first, then the rest
    const first = picks.filter((s) => (seen.has(s.domain) ? false : (seen.add(s.domain), true)));
    return [...first, ...picks].filter((s, i, a) => a.indexOf(s) === i).slice(0, 4);
  });
  warm() { this.api.warmup(); }
}
