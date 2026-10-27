import { ChangeDetectionStrategy, Component, ViewEncapsulation } from '@angular/core';

/** Carries the shared utility styles (kept apart from the shell so each stylesheet stays small). Renders nothing. */
@Component({
  selector: 'eng-styles',
  changeDetection: ChangeDetectionStrategy.OnPush,
  encapsulation: ViewEncapsulation.None,
  template: '',
  styleUrls: ['./utilities.scss', './dialog.scss'],
})
export class StylesComponent {}
