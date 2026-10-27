import { inject } from '@angular/core';
import { CanActivateFn, Router, Routes } from '@angular/router';
import { SessionService } from './core/session.service';

/** Manage and Users are developer pages; the backend enforces it too, this only hides the way in. */
const developerOnly: CanActivateFn = async () => {
  const session = inject(SessionService);
  if (session.loading() && !session.me()) await session.load();
  return session.isDeveloper() ? true : inject(Router).createUrlTree(['/']);
};

export const engismartRoutes: Routes = [
  {
    path: '',
    loadComponent: () => import('./shell/shell.component').then((m) => m.ShellComponent),
    children: [
      { path: '', pathMatch: 'full', redirectTo: 'chat' },
      { path: 'chat', loadComponent: () => import('./chat/chat.page').then((m) => m.ChatPage) },
      { path: 'manage', canActivate: [developerOnly], loadComponent: () => import('./manage/manage.page').then((m) => m.ManagePage) },
      { path: 'users', canActivate: [developerOnly], loadComponent: () => import('./users/users.page').then((m) => m.UsersPage) },
    ],
  },
];
