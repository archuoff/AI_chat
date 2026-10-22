import { FileCode, FileSpreadsheet, FileText, FileType, Presentation, type LucideIcon } from 'lucide-react'
import type { Location } from './types'

type FileVisual = { label: string; Icon: LucideIcon; fg: string; bg: string }

// file types mapped onto Tata Technologies sector colours
const VISUALS: Record<string, FileVisual> = {
  xlsx: { label: 'Excel', Icon: FileSpreadsheet, fg: 'text-tt-auto-dark', bg: 'bg-tt-green-tint' },
  xlsm: { label: 'Excel', Icon: FileSpreadsheet, fg: 'text-tt-auto-dark', bg: 'bg-tt-green-tint' },
  csv: { label: 'CSV', Icon: FileSpreadsheet, fg: 'text-tt-auto-dark', bg: 'bg-tt-green-tint' },
  pdf: { label: 'PDF', Icon: FileText, fg: 'text-tt-ember', bg: 'bg-[#fbe4d9]' },
  docx: { label: 'Word', Icon: FileType, fg: 'text-tt-electric', bg: 'bg-tt-periwinkle/20' },
  pptx: { label: 'PowerPoint', Icon: Presentation, fg: 'text-[#9a5a06]', bg: 'bg-tt-amber-tint' },
  txt: { label: 'Text', Icon: FileCode, fg: 'text-tt-slate', bg: 'bg-tt-line' },
  md: { label: 'Markdown', Icon: FileCode, fg: 'text-tt-slate', bg: 'bg-tt-line' },
}

export const fileVisual = (type: string): FileVisual =>
  VISUALS[type.toLowerCase()] ?? { label: type.toUpperCase(), Icon: FileCode, fg: 'text-tt-slate', bg: 'bg-tt-line' }

export const extOf = (name: string) => name.split('.').pop()?.toLowerCase() ?? ''

export function FileBadge({ type, size = 'md' }: { type: string; size?: 'sm' | 'md' | 'lg' }) {
  const v = fileVisual(type)
  const box = { sm: 'h-7 w-7 rounded-lg', md: 'h-9 w-9 rounded-xl', lg: 'h-11 w-11 rounded-xl' }[size]
  const icon = { sm: 14, md: 17, lg: 20 }[size]
  return (
    <span className={`inline-flex shrink-0 items-center justify-center ${box} ${v.bg} ${v.fg}`}>
      <v.Icon size={icon} strokeWidth={2} />
    </span>
  )
}

export function locationLabel(loc: Location): string {
  const parts: string[] = []
  if (loc.sheet) parts.push(`Sheet ${loc.sheet}`)
  if (loc.page) parts.push(`Page ${loc.page}`)
  if (loc.slide) parts.push(`Slide ${loc.slide}`)
  if (loc.section && !loc.sheet) parts.push(String(loc.section))
  if (loc.table) parts.push(`Table ${loc.table}`)
  if (loc.row) parts.push(`Row ${loc.row}`)
  return parts.join(' · ')
}

export function bytes(n: number): string {
  if (n < 1024) return `${n} B`
  if (n < 1024 ** 2) return `${(n / 1024).toFixed(0)} KB`
  return `${(n / 1024 ** 2).toFixed(1)} MB`
}

export function timeAgo(iso: string | number): string {
  const t = typeof iso === 'number' ? iso : Date.parse(iso)
  const s = Math.max(0, (Date.now() - t) / 1000)
  if (s < 60) return 'just now'
  if (s < 3600) return `${Math.floor(s / 60)} min ago`
  if (s < 86400) return `${Math.floor(s / 3600)} h ago`
  return new Date(t).toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' })
}

export const cleanName = (name: string) => name.replace(/[​]/g, '').replace(/\.{2,}(?=\w+$)/, '.')
