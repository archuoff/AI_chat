import { ChangeDetectionStrategy, Component, computed, effect, inject, OnInit, signal, untracked } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ApiService } from '../core/api.service';
import { domainVisual } from '../core/domains';
import { timeAgo } from '../core/format';
import { SessionService } from '../core/session.service';
import type { Domain, ManagedUser, Role, UsageSummary } from '../core/types';
import { DomainChipComponent } from '../ui/domain-icon.component';
import { IconComponent } from '../ui/icon.component';

const ROLE_INFO: Record<Role, { label: string; text: string; cls: string }> = {
  user: { label: 'User', text: 'Chat only. Selected domains; never sees confidential documents.', cls: 'user' },
  superuser: { label: 'Super user', text: 'Chat across every domain, including confidential documents.', cls: 'super' },
  developer: { label: 'Developer', text: 'Everything: Manage knowledge, ingestion, Users & usage.', cls: 'dev' },
};
const fmt = (n: number) => (n >= 1_000_000 ? `${(n / 1_000_000).toFixed(1)}M` : n >= 1000 ? `${(n / 1000).toFixed(1)}k` : String(n));
const initials = (name: string) => name.split(/[\s._-]+/).filter(Boolean).slice(0, 2).map((s) => s[0]?.toUpperCase()).join('') || '?';

@Component({
  selector: 'eng-users-page',
  imports: [FormsModule, IconComponent, DomainChipComponent],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './users.page.html',
  styleUrl: './users.page.scss',
})
export class UsersPage implements OnInit {
  private readonly api = inject(ApiService);
  readonly session = inject(SessionService);
  readonly users = signal<ManagedUser[] | null>(null);
  readonly usage = signal<UsageSummary | null>(null);
  readonly domains = signal<Domain[]>([]);
  readonly days = signal(30);
  readonly error = signal<string | null>(null);
  readonly editing = signal<ManagedUser | null>(null);
  readonly allowed = signal<string[]>([]);
  readonly saving = signal(false);
  readonly dialogError = signal<string | null>(null);
  readonly finding = signal(false);
  readonly q = signal('');
  readonly found = signal<ManagedUser[]>([]);
  readonly searching = signal(false);

  readonly role = ROLE_INFO;
  readonly fmt = fmt;
  readonly initials = initials;
  readonly ago = timeAgo;
  readonly dv = domainVisual;
  readonly usageById = computed(() => new Map((this.usage()?.per_user ?? []).map((u) => [u.user_id, u])));
  readonly t = computed(() => this.usage()?.totals);
  readonly maxDay = computed(() => Math.max(1, ...(this.usage()?.daily ?? []).map((d) => d.questions)));
  readonly picks = computed(() => this.domains().filter((d) => d.id !== 'unassigned'));
  readonly daysOptions = [7, 30, 90];

  constructor() {
    effect(() => {
      this.days();
      untracked(() => this.load());
    });
  }
  ngOnInit() {
    this.api.domains().then((d) => this.domains.set(d)).catch(() => undefined);
  }

  load() {
    this.api.users().then((u) => { this.users.set(u); this.error.set(null); }).catch((e: Error) => this.error.set(e.message));
    this.api.usage(this.days()).then((u) => this.usage.set(u)).catch(() => undefined);
  }

  edit(u: ManagedUser) {
    this.allowed.set([...u.domains]);
    this.dialogError.set(null);
    this.editing.set(u);
  }
  toggleDomain(id: string) {
    this.allowed.update((cur) => (cur.includes(id) ? cur.filter((x) => x !== id) : [...cur, id]));
  }
  async save() {
    const u = this.editing();
    if (!u) return;
    this.saving.set(true);
    this.dialogError.set(null);
    try {
      await this.api.setUserDomains(u.id, this.allowed());
      this.editing.set(null);
      this.load();
    } catch (e) {
      this.dialogError.set((e as Error).message);
    } finally {
      this.saving.set(false);
    }
  }

  async search() {
    const q = this.q().trim();
    if (q.length < 2) return;
    this.searching.set(true);
    try { this.found.set(await this.api.lookupUsers(q)); } catch (e) { this.dialogError.set((e as Error).message); } finally { this.searching.set(false); }
  }
  pick(u: ManagedUser) {
    this.finding.set(false);
    this.found.set([]);
    this.q.set('');
    this.edit(u);
  }
}
