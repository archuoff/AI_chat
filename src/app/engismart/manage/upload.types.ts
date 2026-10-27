import type { DocRef, IngestResult, SigSize, UploadCheck } from '../core/types';

export type UploadItem = {
  id: string;
  file: File;
  /** queued -> checking (read once, look for similar documents) -> checked (the SME decides) -> uploading -> done */
  state: 'queued' | 'checking' | 'checked' | 'unreadable' | 'uploading' | 'done';
  check?: UploadCheck;
  intent: 'new' | 'update';
  replaces: string;
  allowDuplicate: boolean;
  error?: string;
  result?: IngestResult;
};

const n = (v: number) => v.toLocaleString('en-GB');

/** The new file is much smaller than the document it would replace: everything else would be hidden. */
export function partialWarning(old: SigSize | null | undefined, next: SigSize): string | null {
  if (!old) return null;
  if (old.unit && old.unit === next.unit && old.units >= 2 && next.units < old.units * 0.5)
    return `The existing document has ${old.units} ${old.unit}, this file only ${next.units}. Whatever is missing would no longer be searchable.`;
  const was = old.records + old.text_blocks;
  const now = next.records + next.text_blocks;
  if (was >= 10 && now < was * 0.5) return `The existing document has ${n(was)} items, this file only ${n(now)}. Whatever is missing would no longer be searchable.`;
  return null;
}

/** What stops this file from being added yet (null = ready). */
export function blocker(it: UploadItem): string | null {
  const c = it.check;
  if (!c) return 'Still being checked';
  if (it.intent === 'update') {
    if (!it.replaces) return 'Choose the document this file updates';
    if (c.same_name && c.same_name.doc_id !== it.replaces) return `A different document is already named "${c.same_name.file_name}": rename the file or update that one`;
  } else if (c.same_name) return `A document named "${c.same_name.file_name}" already exists: choose Update, or rename the file`;
  if (c.exact.length && !it.allowDuplicate) return 'This exact file is already in the library: tick "Add anyway" to continue';
  return null;
}

export const chosenDoc = (it: UploadItem): DocRef | undefined => it.check?.others.find((o) => o.doc_id === it.replaces);
