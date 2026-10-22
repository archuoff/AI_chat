import type { CellStatus, ParseOptions } from '../lib/types'

export const colLetter = (n: number) => {
  let s = ''
  while (n > 0) {
    const m = (n - 1) % 26
    s = String.fromCharCode(65 + m) + s
    n = Math.floor((n - 1) / 26)
  }
  return s
}

const colNumber = (letters: string) => letters.split('').reduce((acc, ch) => acc * 26 + ch.charCodeAt(0) - 64, 0)

export function rangeBounds(range: string) {
  const [a, b = a] = range.split(':')
  const pa = a.match(/^([A-Z]+)(\d+)$/)!
  const pb = b.match(/^([A-Z]+)(\d+)$/)!
  return { c0: colNumber(pa[1]), r0: Number(pa[2]), c1: colNumber(pb[1]), r1: Number(pb[2]) }
}

export const STATUS_META: Record<CellStatus, { label: string; cls: string; dot: string; explain: string }> = {
  header: {
    label: 'Header',
    cls: 'bg-tt-navy text-white font-semibold',
    dot: 'bg-tt-navy',
    explain: 'Column heading. Stacked header rows are joined into one path, e.g. "Part Dimensions > Width (mm)".',
  },
  data: {
    label: 'Data',
    cls: 'bg-white text-tt-ink',
    dot: 'bg-white ring-1 ring-tt-line',
    explain: 'Value captured in a record and stored with its column heading.',
  },
  title: {
    label: 'Title / note',
    cls: 'bg-tt-periwinkle/15 text-tt-electric font-semibold',
    dot: 'bg-tt-periwinkle/50',
    explain: 'Single-value line above a table: stored as text; the last one becomes the table title.',
  },
  section: {
    label: 'Section',
    cls: 'bg-tt-teal/15 text-[#0b6f64] font-semibold',
    dot: 'bg-tt-teal/60',
    explain: 'Single-value row inside a table: labels every following row as a section.',
  },
  ignored: {
    label: 'Ignored',
    cls: 'bg-[repeating-linear-gradient(135deg,#f4f5fb_0_6px,#eceef7_6px_12px)] text-tt-slate/60 italic',
    dot: 'bg-[repeating-linear-gradient(135deg,#d9dcea_0_3px,#f4f5fb_3px_6px)]',
    explain: 'Picture placed in a cell, Excel error (#VALUE!) or placeholder text: nothing readable to store.',
  },
  missed: {
    label: 'Not captured',
    cls: 'bg-[#fde8df] text-[#8a3510] ring-1 ring-inset ring-tt-ember/70',
    dot: 'bg-[#f6b79c]',
    explain: 'Has a value but was not stored. Adjust the table detection (header rows) or report it.',
  },
  skipped: {
    label: 'Excluded',
    cls: 'bg-tt-mist text-tt-slate/45 line-through',
    dot: 'bg-tt-line',
    explain: 'Excluded by your correction: not stored in the knowledge base.',
  },
}

export const optionsEqual = (a: ParseOptions | undefined, b: ParseOptions | undefined) =>
  JSON.stringify(normalize(a)) === JSON.stringify(normalize(b))

/** Drop empty entries so {} and {tables: {}} compare equal. */
export function normalize(o: ParseOptions | undefined): ParseOptions {
  const out: ParseOptions = {}
  const sheets = Object.entries(o?.sheets ?? {}).filter(([, v]) => v?.skip)
  if (sheets.length) out.sheets = Object.fromEntries(sheets.sort())
  const tables = Object.entries(o?.tables ?? {})
    .map(([k, v]) => [k, Object.fromEntries(Object.entries(v ?? {}).filter(([, x]) => x !== null && x !== undefined && x !== false))] as const)
    .filter(([, v]) => Object.keys(v).length)
  if (tables.length) out.tables = Object.fromEntries(tables.sort())
  return out
}
