import { ChangeDetectionStrategy, Component, effect, inject, input, signal } from '@angular/core';
import { ApiService } from '../core/api.service';
import { IconComponent } from './icon.component';

// object URLs per picture, kept for the session (thumbnails are small; the same picture shows in several places)
const cache = new Map<string, Promise<string>>();

/** <img> for a document picture. The API needs the platform token, so the file is fetched through HttpClient, not linked. */
@Component({
  selector: 'eng-auth-image',
  imports: [IconComponent],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    @if (failed()) { <span class="ph"><eng-icon name="image-off" [size]="18" /></span> }
    @else if (!src()) { <span class="ph pulse"></span> }
    @else { <img [src]="src()" [alt]="alt()" draggable="false" /> }`,
  styles: [`
    :host { display: block; } img { display: block; width: 100%; height: 100%; object-fit: contain; }
    .ph { display: flex; width: 100%; height: 100%; min-height: 40px; align-items: center; justify-content: center; background: var(--eng-mist, #eef0f8); color: #8a8fa8; }
    .pulse { animation: p 1.2s ease-in-out infinite; } @keyframes p { 50% { opacity: 0.5; } }`],
})
export class AuthImageComponent {
  private readonly api = inject(ApiService);
  readonly id = input.required<string>();
  readonly thumb = input(true);
  readonly alt = input('');
  readonly src = signal<string | null>(null);
  readonly failed = signal(false);

  constructor() {
    effect((onCleanup) => {
      const id = this.id(), thumb = this.thumb();
      this.src.set(null);
      this.failed.set(false);
      const key = `${id}:${thumb}`;
      let p = cache.get(key);
      if (!p) {
        p = this.api.imageBlob(id, thumb).then((b) => URL.createObjectURL(b));
        p.catch(() => cache.delete(key));
        cache.set(key, p);
      }
      let live = true;
      p.then((u) => live && this.src.set(u), () => live && this.failed.set(true));
      onCleanup(() => { live = false; });
    });
  }
}
