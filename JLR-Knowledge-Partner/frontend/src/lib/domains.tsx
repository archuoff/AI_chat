import clsx from 'clsx'
import { Atom, ChartColumn, CircleDashed, DraftingCompass, Factory, GraduationCap, LayoutGrid, Radar, type LucideIcon } from 'lucide-react'

type Visual = { Icon: LucideIcon; color: string; tint: string; label: string }

// Domain identities, drawn from the Tata Technologies palette
export const DOMAIN_VISUALS: Record<string, Visual> = {
  all: { Icon: LayoutGrid, color: '#001B5B', tint: '#E3E6F2', label: 'All domains' },
  adas: { Icon: Radar, color: '#0B8F81', tint: '#D7F5F1', label: 'ADAS' },
  benchmarking: { Icon: ChartColumn, color: '#0000B3', tint: '#E1E3FF', label: 'Benchmarking' },
  eds: { Icon: DraftingCompass, color: '#3D5FE0', tint: '#E4EAFE', label: 'EDS' },
  'lead-engineering': { Icon: GraduationCap, color: '#B86A0B', tint: '#FDF0DC', label: 'Lead Engineering' },
  'materials-net': { Icon: Atom, color: '#9B2FD6', tint: '#F3E5FC', label: 'Materials Net' },
  'supplier-database': { Icon: Factory, color: '#163D51', tint: '#DDEFD8', label: 'Supplier Database' },
  unassigned: { Icon: CircleDashed, color: '#4E4B66', tint: '#ECECF2', label: 'Unassigned' },
}

export const domainVisual = (id?: string | null): Visual => DOMAIN_VISUALS[id || 'unassigned'] ?? DOMAIN_VISUALS.unassigned

export function DomainIcon({ id, size = 'md' }: { id?: string | null; size?: 'sm' | 'md' | 'lg' }) {
  const v = domainVisual(id)
  const box = { sm: 'h-6 w-6 rounded-md', md: 'h-9 w-9 rounded-xl', lg: 'h-11 w-11 rounded-2xl' }[size]
  const icon = { sm: 13, md: 17, lg: 21 }[size]
  return (
    <span className={clsx('inline-flex shrink-0 items-center justify-center', box)} style={{ color: v.color, background: v.tint }}>
      <v.Icon size={icon} strokeWidth={2.1} />
    </span>
  )
}

export function DomainChip({ id, name }: { id?: string | null; name?: string }) {
  const v = domainVisual(id)
  return (
    <span
      className="inline-flex items-center gap-1 rounded-md px-1.5 py-0.5 text-[11px] font-semibold whitespace-nowrap"
      style={{ color: v.color, background: v.tint }}
    >
      <v.Icon size={11} strokeWidth={2.4} />
      {name ?? v.label}
    </span>
  )
}
