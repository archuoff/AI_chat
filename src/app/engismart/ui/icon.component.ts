import { ChangeDetectionStrategy, Component, computed, input } from '@angular/core';

const circle = (cx: number, cy: number, r: number) => `M${cx - r} ${cy}a${r} ${r} 0 1 0 ${2 * r} 0a${r} ${r} 0 1 0 ${-2 * r} 0`;
const rect = (x: number, y: number, w: number, h: number, r = 2) =>
  `M${x + r} ${y}h${w - 2 * r}a${r} ${r} 0 0 1 ${r} ${r}v${h - 2 * r}a${r} ${r} 0 0 1 ${-r} ${r}h${-(w - 2 * r)}a${r} ${r} 0 0 1 ${-r} ${-r}v${-(h - 2 * r)}a${r} ${r} 0 0 1 ${r} ${-r}z`;

/** Line icons (24x24 grid, stroke only). */
const ICONS: Record<string, string[]> = {
  check: ['M20 6 9 17l-5-5'],
  x: ['M18 6 6 18', 'M6 6l12 12'],
  plus: ['M5 12h14', 'M12 5v14'],
  minus: ['M5 12h14'],
  'chevron-down': ['m6 9 6 6 6-6'],
  'chevron-right': ['m9 18 6-6-6-6'],
  'chevron-left': ['m15 18-6-6 6-6'],
  'arrow-up': ['m5 12 7-7 7 7', 'M12 19V5'],
  'arrow-down': ['M12 5v14', 'm19 12-7 7-7-7'],
  'arrow-right': ['M5 12h14', 'm12 5 7 7-7 7'],
  square: [rect(5, 5, 14, 14, 2)],
  paperclip: ['m21.44 11.05-9.19 9.19a6 6 0 0 1-8.49-8.49l8.57-8.57A4 4 0 1 1 18 8.84l-8.59 8.57a2 2 0 0 1-2.83-2.83l8.49-8.48'],
  copy: [rect(9, 9, 13, 13, 2), 'M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1'],
  info: [circle(12, 12, 10), 'M12 16v-4', 'M12 8h.01'],
  layers: ['m12 2 10 5-10 5L2 7z', 'm2 17 10 5 10-5', 'm2 12 10 5 10-5'],
  alert: ['m21.73 18-8-14a2 2 0 0 0-3.46 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3', 'M12 9v4', 'M12 17h.01'],
  zap: ['M13 2 3 14h9l-1 8 10-12h-9z'],
  book: ['M2 3h6a4 4 0 0 1 4 4v14a3 3 0 0 0-3-3H2z', 'M22 3h-6a4 4 0 0 0-4 4v14a3 3 0 0 1 3-3h7z'],
  pin: ['M20 10c0 6-8 12-8 12s-8-6-8-12a8 8 0 0 1 16 0', circle(12, 10, 3)],
  image: [rect(3, 3, 18, 18, 2), circle(9, 9, 2), 'm21 15-3.09-3.09a2 2 0 0 0-2.82 0L6 21'],
  'image-plus': ['M16 5h6', 'M19 2v6', 'M21 11.5V19a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h7.5', 'm21 15-3.09-3.09a2 2 0 0 0-2.82 0L6 21', circle(9, 9, 2)],
  'image-off': ['M2 2l20 20', 'M10.41 10.41a2 2 0 1 1-2.83-2.83', 'M13.5 3H19a2 2 0 0 1 2 2v11.5', 'M21 15l-3.09-3.09a2 2 0 0 0-1.38-.6', 'M21 21H5a2 2 0 0 1-2-2V5'],
  loader: ['M21 12a9 9 0 1 1-6.219-8.56'],
  message: ['M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z'],
  library: ['M20 20a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-7.9a2 2 0 0 1-1.69-.9L9.6 3.9A2 2 0 0 0 7.93 3H4a2 2 0 0 0-2 2v13a2 2 0 0 0 2 2z'],
  users: ['M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2', circle(9, 7, 4), 'M22 21v-2a4 4 0 0 0-3-3.87', 'M16 3.13a4 4 0 0 1 0 7.75'],
  trash: ['M3 6h18', 'M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6', 'M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2', 'M10 11v6', 'M14 11v6'],
  upload: ['M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4', 'm17 8-5-5-5 5', 'M12 3v12'],
  refresh: ['M3 12a9 9 0 0 1 9-9 9.75 9.75 0 0 1 6.74 2.74L21 8', 'M21 3v5h-5', 'M21 12a9 9 0 0 1-9 9 9.75 9.75 0 0 1-6.74-2.74L3 16', 'M8 16H3v5'],
  search: [circle(11, 11, 8), 'm21 21-4.3-4.3'],
  eye: ['M2 12s3-7 10-7 10 7 10 7-3 7-10 7-10-7-10-7', circle(12, 12, 3)],
  lock: [rect(3, 11, 18, 11, 2), 'M7 11V7a5 5 0 0 1 10 0v4'],
  unlock: [rect(3, 11, 18, 11, 2), 'M7 11V7a5 5 0 0 1 9.9-1'],
  menu: ['M4 6h16', 'M4 12h16', 'M4 18h16'],
  panel: [rect(3, 3, 18, 18, 2), 'M15 3v18'],
  sparkles: ['m12 3-1.9 5.8a2 2 0 0 1-1.3 1.3L3 12l5.8 1.9a2 2 0 0 1 1.3 1.3L12 21l1.9-5.8a2 2 0 0 1 1.3-1.3L21 12l-5.8-1.9a2 2 0 0 1-1.3-1.3z'],
  undo: ['M3 7v6h6', 'M21 17a9 9 0 0 0-9-9 9 9 0 0 0-6 2.3L3 13'],
  file: ['M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7z', 'M14 2v4a2 2 0 0 0 2 2h4', 'M10 9H8', 'M16 13H8', 'M16 17H8'],
  doc: ['M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7z', 'M14 2v4a2 2 0 0 0 2 2h4', 'M9 13h6', 'M9 17h6'],
  sheet: ['M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7z', 'M14 2v4a2 2 0 0 0 2 2h4', 'M8 13h8', 'M8 17h8', 'M12 11v8'],
  slides: [rect(2, 3, 20, 14, 2), 'M8 21h8', 'M12 17v4'],
  code: ['m16 18 6-6-6-6', 'm8 6-6 6 6 6'],
  grid: [rect(3, 3, 7, 7, 1), rect(14, 3, 7, 7, 1), rect(14, 14, 7, 7, 1), rect(3, 14, 7, 7, 1)],
  radar: ['M19.07 4.93A10 10 0 0 0 6.99 3.34', 'M4 6h.01', 'M2.29 9.62A10 10 0 1 0 21.31 8.35', 'M16.24 7.76A6 6 0 1 0 8.23 16.67', 'M12 18h.01', 'M17.99 11.66A6 6 0 0 1 15.77 16.67', circle(12, 12, 2), 'm13.41 10.59 5.66-5.66'],
  chart: ['M18 20V10', 'M12 20V4', 'M6 20v-6'],
  compass: ['m16.24 7.76-1.804 5.411a2 2 0 0 1-1.265 1.265L7.76 16.24l1.804-5.411a2 2 0 0 1 1.265-1.265z', circle(12, 12, 10)],
  cap: ['M22 10v6', 'M2 10l10-5 10 5-10 5z', 'M6 12v5c3 3 9 3 12 0v-5'],
  atom: [circle(12, 12, 1), 'M20.2 20.2c2.04-2.03.02-7.36-4.5-11.9-4.54-4.52-9.87-6.54-11.9-4.5-2.04 2.03-.02 7.36 4.5 11.9 4.54 4.52 9.87 6.54 11.9 4.5', 'M15.7 15.7c4.52-4.54 6.54-9.87 4.5-11.9-2.03-2.04-7.36-.02-11.9 4.5-4.52 4.54-6.54 9.87-4.5 11.9 2.03 2.04 7.36.02 11.9-4.5'],
  factory: ['M2 20a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2V8l-7 5V8l-7 5V4a2 2 0 0 0-2-2H4a2 2 0 0 0-2 2z', 'M17 18h1', 'M12 18h1', 'M7 18h1'],
  dashed: [circle(12, 12, 10)],
  shield: ['M20 13c0 5-3.5 7.5-7.66 8.95a1 1 0 0 1-.67-.01C7.5 20.5 4 18 4 13V6a1 1 0 0 1 1-1c2 0 4.5-1.2 6.24-2.72a1.17 1.17 0 0 1 1.52 0C14.51 3.81 17 5 19 5a1 1 0 0 1 1 1z'],
  table: [rect(3, 3, 18, 18, 2), 'M3 9h18', 'M3 15h18', 'M9 3v18'],
  more: [circle(12, 12, 1), circle(19, 12, 1), circle(5, 12, 1)],
  edit: ['M12 20h9', 'M16.5 3.5a2.12 2.12 0 0 1 3 3L7 19l-4 1 1-4z'],
  clock: [circle(12, 12, 10), 'M12 6v6l4 2'],
};

@Component({
  selector: 'eng-icon',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `<svg [attr.width]="size()" [attr.height]="size()" viewBox="0 0 24 24" fill="none" stroke="currentColor" [attr.stroke-width]="stroke()"
                   stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" [class.eng-spin]="spin()">
    @for (d of paths(); track $index) { <path [attr.d]="d" /> }
  </svg>`,
  styles: [`:host { display: inline-flex; flex: none; line-height: 0; } .eng-spin { animation: eng-spin 0.9s linear infinite; } @keyframes eng-spin { to { transform: rotate(360deg); } }`],
})
export class IconComponent {
  readonly name = input.required<string>();
  readonly size = input(16);
  readonly stroke = input(2);
  readonly spin = input(false);
  readonly paths = computed(() => ICONS[this.name()] ?? ICONS['dashed']);
}
