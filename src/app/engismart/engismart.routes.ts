import { inject } from '@angular/core';
import { CanActivateFn, Router, Routes } from '@angular/router';
import { SessionService } from './core/session.service';

/** Manage knowledge is for superusers and developers; the backend enforces it too, this only hides the way in. */
const developerOnly: CanActivateFn = async (_route, state) => {
  const session = inject(SessionService);
  const router = inject(Router); // inject() only works before the first await
  if (!session.me()) await session.load();
  // send the person to the chat of this same remote (the remote may be mounted under any prefix in the host)
  return session.canManage() ? true : router.parseUrl(state.url.replace(/\/manage(?=[/?#]|$).*$/, '/chat'));
};

export const engismartRoutes: Routes = [
  {
    path: '',
    loadComponent: () => import('./shell/shell.component').then((m) => m.ShellComponent),
    children: [
      { path: '', pathMatch: 'full', redirectTo: 'chat' },
      { path: 'chat', loadComponent: () => import('./chat/chat.page').then((m) => m.ChatPage) },
      { path: 'manage', canActivate: [developerOnly], loadComponent: () => import('./manage/manage.page').then((m) => m.ManagePage) },
    ],
  },
];
