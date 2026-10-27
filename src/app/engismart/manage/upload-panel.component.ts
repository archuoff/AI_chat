import { ChangeDetectionStrategy, Component, computed, effect, ElementRef, inject, input, output, signal, untracked, viewChild } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ApiService } from '../core/api.service';
import { domainVisual } from '../core/domains';
import { bytes, extOf } from '../core/format';
import type { Domain } from '../core/types';
import { FileBadgeComponent } from '../ui/file-badge.component';
import { IconComponent } from '../ui/icon.component';
import { UploadDecisionComponent } from './upload-decision.component';
import { blocker, UploadItem } from './upload.types';

const ACCEPT = ['.xlsx', '.xlsm', '.csv', '.pdf', '.docx', '.pptx', '.txt', '.md'];
const DOC_TYPES = ['Benchmarking', 'Design guideline', 'FMEA', 'Control plan', 'Specification', 'Issue log', 'Lessons learned', 'Other'];
type Field = { key: string; value: string };

@Component({
  selector: 'eng-upload-panel',
  imports: [FormsModule, IconComponent, FileBadgeComponent, UploadDecisionComponent],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './upload-panel.component.html',
  styleUrl: './upload-panel.component.scss',
})
export class UploadPanelComponent {
  private readonly api = inject(ApiService);
  readonly domains = input<Domain[]>([]);
  readonly done = output<void>();
  readonly closed = output<void>();
  readonly items = signal<UploadItem[]>([]);
  readonly domain = signal('');
  readonly drag = signal(false);
  readonly running = signal(false);
  readonly project = signal('');
  readonly docType = signal('');
  readonly department = signal('');
  readonly tags = signal('');
  readonly custom = signal<Field[]>([]);
  readonly force = signal(false);
  readonly fileInput = viewChild<ElementRef<HTMLInputElement>>('files');

  readonly accept = ACCEPT.join(',');
  readonly docTypes = DOC_TYPES;
  readonly dv = domainVisual;
  readonly ext = extOf;
  readonly size = bytes;
  readonly ready = computed(() => this.items().filter((i) => i.state === 'checked' && !blocker(i)).length);
  readonly waiting = computed(() => this.items().filter((i) => i.state === 'queued' || i.state === 'checking').length);
  readonly allDone = computed(() => this.items().length > 0 && this.items().every((i) => i.state === 'done'));

  constructor() {
    // files are checked one at a time (reading a big workbook takes a moment)
    effect(() => {
      const items = this.items();
      if (items.some((i) => i.state === 'checking')) return;
      const next = items.find((i) => i.state === 'queued');
      if (!next) return;
      untracked(() => {
        this.patch(next.id, { state: 'checking', error: undefined });
        this.api.checkUpload(next.file, this.domain()).then((check) => {
          const top = check.suggestions[0];
          // pre-select "update" only when the system is sure; otherwise the SME picks
          const update = top?.label === 'likely' && !check.exact.some((e) => !e.superseded);
          this.patch(next.id, { state: 'checked', check, intent: update ? 'update' : 'new', replaces: update ? top.doc_id : '' });
        }).catch((e: Error) => this.patch(next.id, { state: 'unreadable', error: e.message }));
      });
    });
  }

  patch(id: string, change: Partial<UploadItem>) {
    this.items.update((cur) => cur.map((c) => (c.id === id ? { ...c, ...change } : c)));
  }

  add(files: FileList | null) {
    if (!files) return;
    const next: UploadItem[] = Array.from(files).filter((f) => ACCEPT.includes(`.${extOf(f.name)}`)).map((file) => ({
      id: `${file.name}-${file.size}-${file.lastModified}`, file, state: 'queued', intent: 'new', replaces: '', allowDuplicate: false }));
    this.items.update((cur) => [...cur.filter((c) => c.state !== 'done'), ...next.filter((n) => !cur.some((c) => c.id === n.id))]);
  }
  remove(id: string) { this.items.update((c) => c.filter((x) => x.id !== id)); }
  removable = (it: UploadItem) => it.state === 'queued' || it.state === 'checked' || it.state === 'unreadable';
  onDrop(e: DragEvent) { e.preventDefault(); this.drag.set(false); this.add(e.dataTransfer?.files ?? null); }
  onDrag(e: DragEvent) { e.preventDefault(); this.drag.set(true); }
  pick(e: Event) { this.add((e.target as HTMLInputElement).files); }
  addField() { this.custom.update((c) => [...c, { key: '', value: '' }]); }
  setField(i: number, part: 'key' | 'value', v: string) { this.custom.update((c) => c.map((x, j) => (j === i ? { ...x, [part]: v } : x))); }
  removeField(i: number) { this.custom.update((c) => c.filter((_, j) => j !== i)); }

  private meta(): Record<string, unknown> {
    const m: Record<string, unknown> = {};
    if (this.project().trim()) m['project'] = this.project().trim();
    if (this.docType()) m['doc_type'] = this.docType();
    if (this.department().trim()) m['department'] = this.department().trim();
    const t = this.tags().split(',').map((x) => x.trim()).filter(Boolean);
    if (t.length) m['tags'] = t;
    for (const f of this.custom()) if (f.key.trim() && f.value.trim()) m[f.key.trim()] = f.value.trim();
    return m;
  }

  async run() {
    this.running.set(true);
    const m = this.meta();
    for (const it of this.items().filter((i) => i.state === 'checked' && !blocker(i))) {
      this.patch(it.id, { state: 'uploading', error: undefined });
      try {
        const result = await this.api.commitUpload({ check_id: it.check!.check_id, intent: it.intent, replaces: it.intent === 'update' ? it.replaces : undefined,
          domain: this.domain(), metadata: m, force: this.force(), allow_duplicate: it.allowDuplicate });
        if (result.status === 'failed') this.patch(it.id, { state: 'checked', error: result.error ?? 'Processing failed' });
        else this.patch(it.id, { state: 'done', result });
      } catch (e) {
        this.patch(it.id, { state: 'checked', error: (e as Error).message });
      }
    }
    this.running.set(false);
    this.done.emit();
  }
}
