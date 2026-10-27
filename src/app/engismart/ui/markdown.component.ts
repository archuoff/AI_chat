import { ChangeDetectionStrategy, Component, ElementRef, effect, inject, input, output } from '@angular/core';
import DOMPurify from 'dompurify';
import { marked } from 'marked';

marked.setOptions({ gfm: true, breaks: false });

/** Answer markdown to safe HTML; [n] citations become clickable chips, tables get a scroll wrapper. */
export function renderMarkdown(text: string): string {
  const linked = text.replace(/\[(\d{1,3})\](?!\()/g, '<button type="button" class="cite" data-n="$1" title="Show source $1">$1</button>');
  const html = marked.parse(linked, { async: false }) as string;
  const clean = DOMPurify.sanitize(html, { ADD_ATTR: ['target'], FORBID_TAGS: ['style', 'script', 'iframe'] });
  return clean.replace(/<table/g, '<div class="table-wrap"><table').replace(/<\/table>/g, '</table></div>').replace(/<a /g, '<a target="_blank" rel="noreferrer noopener" ');
}

@Component({
  selector: 'eng-markdown',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: '',
  host: { '[class.caret]': 'streaming()', class: 'md', '(click)': 'clicked($event)' },
})
export class MarkdownComponent {
  private readonly el = inject<ElementRef<HTMLElement>>(ElementRef);
  readonly text = input.required<string>();
  readonly streaming = input(false);
  readonly cite = output<number>();

  constructor() {
    effect(() => {
      this.el.nativeElement.innerHTML = renderMarkdown(this.text());
    });
  }

  clicked(ev: MouseEvent) {
    const btn = (ev.target as HTMLElement).closest?.('button.cite') as HTMLElement | null;
    if (btn) this.cite.emit(Number(btn.dataset['n']));
  }
}
