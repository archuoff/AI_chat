import type { CellStatus, ParseOptions } from '../core/types';

export const colLetter = (n: number): string => {
  let s = '';
  while (n > 0) {
    const m = (n - 1) % 26;
    s = String.fromCharCode(65 + m) + s;
    n = Math.floor((n - 1) / 26);
  }
  return s;
};

const colNumber = (letters: string) => letters.split('').reduce((acc, ch) => acc * 26 + ch.charCodeAt(0) - 64, 0);

export function rangeBounds(range: string) {
  const [a, b = a] = range.split(':');
  const pa = a.match(/^([A-Z]+)(\d+)$/)!;
  const pb = b.match(/^([A-Z]+)(\d+)$/)!;
  return { c0: colNumber(pa[1]), r0: Number(pa[2]), c1: colNumber(pb[1]), r1: Number(pb[2]) };
}

export const STATUS_META: Record<CellStatus, { label: string; explain: string }> = {
  header: { label: 'Header', explain: 'Column heading. Stacked header rows are joined into one path, e.g. "Part Dimensions > Width (mm)".' },
  data: { label: 'Data', explain: 'Value captured in a record and stored with its column heading.' },
  title: { label: 'Title / note', explain: 'Single-value line above a table: stored as text; the last one becomes the table title.' },
  section: { label: 'Section', explain: 'Single-value row inside a table: labels every following row as a section.' },
  ignored: { label: 'Ignored', explain: 'Picture placed in a cell, Excel error (#VALUE!) or placeholder text: nothing readable to store.' },
  missed: { label: 'Not captured', explain: 'Has a value but was not stored. Adjust the table detection (header rows) or report it.' },
  skipped: { label: 'Excluded', explain: 'Excluded by your correction: not stored in the knowledge base.' },
};
export const STATUS_ORDER = Object.keys(STATUS_META) as CellStatus[];

/** Drop empty entries so {} and {tables: {}} compare equal. */
export function normalize(o: ParseOptions | undefined): ParseOptions {
  const out: ParseOptions = {};
  const sheets = Object.entries(o?.sheets ?? {}).filter(([, v]) => v?.skip);
  if (sheets.length) out.sheets = Object.fromEntries(sheets.sort());
  const tables = Object.entries(o?.tables ?? {})
    .map(([k, v]) => [k, Object.fromEntries(Object.entries(v ?? {}).filter(([, x]) => x !== null && x !== undefined && x !== false))] as const)
    .filter(([, v]) => Object.keys(v).length);
  if (tables.length) out.tables = Object.fromEntries(tables.sort());
  return out;
}

export const optionsEqual = (a: ParseOptions | undefined, b: ParseOptions | undefined): boolean => JSON.stringify(normalize(a)) === JSON.stringify(normalize(b));
