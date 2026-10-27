import { HttpInterceptorFn } from '@angular/common/http';
import { environment } from '../../../environments/environment';
import { API_BASE } from './env';

/**
 * ONLY for running this remote on its own (`ng serve`), where no host exists to add the platform token.
 * It is wired in app.config.ts, which the host never loads; hosted, the host's own interceptor does this job.
 * Token: `devToken` in the environment file, or localStorage key `engismart.devToken` (paste a token in the browser console).
 */
export const devTokenInterceptor: HttpInterceptorFn = (req, next) => {
  if (!req.url.startsWith(API_BASE) || req.headers.has('access-token')) return next(req);
  let token = ((environment as Record<string, unknown>)['devToken'] as string | undefined) ?? '';
  try {
    token = token || localStorage.getItem('engismart.devToken') || '';
  } catch { /* storage blocked */ }
  return token ? next(req.clone({ setHeaders: { 'access-token': token } })) : next(req);
};
