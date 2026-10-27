import { computed, inject, Injectable, signal } from '@angular/core';
import { ApiService } from './api.service';
import type { Me } from './types';

/** Who the platform says is using Engismart (role and allowed domains come from the backend, never from the browser). */
@Injectable({ providedIn: 'root' })
export class SessionService {
  private readonly api = inject(ApiService);
  readonly me = signal<Me | null>(null);
  readonly error = signal<string | null>(null);
  readonly loading = signal(true);
  readonly isDeveloper = computed(() => this.me()?.role === 'developer');

  async load(): Promise<void> {
    this.loading.set(true);
    try {
      this.me.set(await this.api.me());
      this.error.set(null);
    } catch (e) {
      this.me.set(null);
      this.error.set((e as Error).message);
    } finally {
      this.loading.set(false);
    }
  }
}
