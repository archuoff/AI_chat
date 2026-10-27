import { ChangeDetectionStrategy, Component, inject, OnInit, ViewEncapsulation } from '@angular/core';
import { RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';
import { SessionService } from '../core/session.service';
import { IconComponent } from '../ui/icon.component';
import { StylesComponent } from '../ui/styles.component';

/** The frame of the remote: a slim tab bar (Chat / Manage / Users) inside the host's layout. Role comes from the backend. */
@Component({
  selector: 'eng-shell',
  imports: [RouterOutlet, RouterLink, RouterLinkActive, IconComponent, StylesComponent],
  changeDetection: ChangeDetectionStrategy.OnPush,
  encapsulation: ViewEncapsulation.None,
  templateUrl: './shell.component.html',
  styleUrl: './shell.component.scss',
})
export class ShellComponent implements OnInit {
  readonly session = inject(SessionService);
  ngOnInit() {
    void this.session.load();
  }
  reload() {
    void this.session.load();
  }
}
