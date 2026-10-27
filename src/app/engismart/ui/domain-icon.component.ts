import { ChangeDetectionStrategy, Component, computed, input } from '@angular/core';
import { domainVisual } from '../core/domains';
import { IconComponent } from './icon.component';

@Component({
  selector: 'eng-domain-icon',
  imports: [IconComponent],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `<span class="d" [class]="'d ' + size()" [style.color]="v().color" [style.background]="v().tint"><eng-icon [name]="v().icon" [size]="px()" [stroke]="2.1" /></span>`,
  styles: [`
    .d { display: inline-flex; flex: none; align-items: center; justify-content: center; }
    .sm { width: 24px; height: 24px; border-radius: 6px; } .md { width: 36px; height: 36px; border-radius: 12px; } .lg { width: 44px; height: 44px; border-radius: 16px; }`],
})
export class DomainIconComponent {
  readonly id = input<string | null | undefined>('unassigned');
  readonly size = input<'sm' | 'md' | 'lg'>('md');
  readonly v = computed(() => domainVisual(this.id()));
  readonly px = computed(() => ({ sm: 13, md: 17, lg: 21 })[this.size()]);
}

@Component({
  selector: 'eng-domain-chip',
  imports: [IconComponent],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `<span class="chip" [style.color]="v().color" [style.background]="v().tint"><eng-icon [name]="v().icon" [size]="11" [stroke]="2.4" />{{ name() ?? v().label }}</span>`,
  styles: [`.chip { display: inline-flex; align-items: center; gap: 4px; border-radius: 6px; padding: 2px 6px; font-size: 11px; font-weight: 600; white-space: nowrap; }`],
})
export class DomainChipComponent {
  readonly id = input<string | null | undefined>('unassigned');
  readonly name = input<string | undefined>(undefined);
  readonly v = computed(() => domainVisual(this.id()));
}
