export type DomainVisual = { icon: string; color: string; tint: string; label: string };

// Domain identities, drawn from the Tata Technologies palette
export const DOMAIN_VISUALS: Record<string, DomainVisual> = {
  all: { icon: 'grid', color: '#001B5B', tint: '#E3E6F2', label: 'All domains' },
  adas: { icon: 'radar', color: '#0B8F81', tint: '#D7F5F1', label: 'ADAS' },
  benchmarking: { icon: 'chart', color: '#0000B3', tint: '#E1E3FF', label: 'Benchmarking' },
  eds: { icon: 'compass', color: '#3D5FE0', tint: '#E4EAFE', label: 'EDS' },
  'lead-engineering': { icon: 'cap', color: '#B86A0B', tint: '#FDF0DC', label: 'Lead Engineering' },
  'materials-net': { icon: 'atom', color: '#9B2FD6', tint: '#F3E5FC', label: 'Materials Net' },
  'supplier-database': { icon: 'factory', color: '#163D51', tint: '#DDEFD8', label: 'Supplier Database' },
  unassigned: { icon: 'dashed', color: '#4E4B66', tint: '#ECECF2', label: 'Unassigned' },
};

export const domainVisual = (id?: string | null): DomainVisual => DOMAIN_VISUALS[id || 'unassigned'] ?? DOMAIN_VISUALS['unassigned'];
