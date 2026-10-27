import type { Location } from './types';

export type FileVisual = { label: string; icon: string; fg: string; bg: string };

// file types mapped onto the palette
const VISUALS: Record<string, FileVisual> = {
  xlsx: { label: 'Excel', icon: 'sheet', fg: '#0b6f64', bg: '#d7f5f1' },
  xlsm: { label: 'Excel', icon: 'sheet', fg: '#0b6f64', bg: '#d7f5f1' },
  csv: { label: 'CSV', icon: 'sheet', fg: '#0b6f64', bg: '#d7f5f1' },
  pdf: { label: 'PDF', icon: 'file', fg: '#c2410c', bg: '#fbe4d9' },
  docx: { label: 'Word', icon: 'doc', fg: '#0000b3', bg: '#e1e3ff' },
  pptx: { label: 'PowerPoint', icon: 'slides', fg: '#9a5a06', bg: '#fdf0dc' },
  txt: { label: 'Text', icon: 'code', fg: '#4e4b66', bg: '#ececf2' },
  md: { label: 'Markdown', icon: 'code', fg: '#4e4b66', bg: '#ececf2' },
};

export const fileVisual = (type: string): FileVisual =>
  VISUALS[type.toLowerCase()] ?? { label: type.toUpperCase(), icon: 'code', fg: '#4e4b66', bg: '#ececf2' };

export const extOf = (name: string) => name.split('.').pop()?.toLowerCase() ?? '';

export function locationLabel(loc: Location): string {
  const parts: string[] = [];
  if (loc['sheet']) parts.push(`Sheet ${loc['sheet']}`);
  if (loc['page']) parts.push(`Page ${loc['page']}`);
  if (loc['slide']) parts.push(`Slide ${loc['slide']}`);
  if (loc['section'] && !loc['sheet']) parts.push(String(loc['section']));
  if (loc['table']) parts.push(`Table ${loc['table']}`);
  if (loc['row']) parts.push(`Row ${loc['row']}`);
  return parts.join(' · ');
}

export function bytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 ** 2) return `${(n / 1024).toFixed(0)} KB`;
  return `${(n / 1024 ** 2).toFixed(1)} MB`;
}

export function timeAgo(iso: string | number): string {
  const t = typeof iso === 'number' ? iso : Date.parse(iso);
  const s = Math.max(0, (Date.now() - t) / 1000);
  if (s < 60) return 'just now';
  if (s < 3600) return `${Math.floor(s / 60)} min ago`;
  if (s < 86400) return `${Math.floor(s / 3600)} h ago`;
  return new Date(t).toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' });
}

export const cleanName = (name: string) => name.replace(/[​]/g, '').replace(/\.{2,}(?=\w+$)/, '.');
