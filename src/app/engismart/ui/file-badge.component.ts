import { ChangeDetectionStrategy, Component, computed, input } from '@angular/core';
import { fileVisual } from '../core/format';
import { IconComponent } from './icon.component';

@Component({
  selector: 'eng-file-badge',
  imports: [IconComponent],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `<span class="badge" [class]="'badge ' + size()" [style.color]="v().fg" [style.background]="v().bg" [title]="v().label"><eng-icon [name]="v().icon" [size]="px()" /></span>`,
  styles: [`
    .badge { display: inline-flex; flex: none; align-items: center; justify-content: center; }
    .sm { width: 28px; height: 28px; border-radius: 8px; } .md { width: 36px; height: 36px; border-radius: 12px; } .lg { width: 44px; height: 44px; border-radius: 12px; }`],
})
export class FileBadgeComponent {
  readonly type = input.required<string>();
  readonly size = input<'sm' | 'md' | 'lg'>('md');
  readonly v = computed(() => fileVisual(this.type()));
  readonly px = computed(() => ({ sm: 14, md: 17, lg: 20 })[this.size()]);
}
