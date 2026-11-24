import { environment } from '../../../environments/environment';

/** The backend address, including the platform prefix, e.g. http://localhost:8002 or https://host/api/v1 (set in the environment files). */
export const API_ROOT: string = ((environment as Record<string, unknown>)['engismartUrl'] as string | undefined)?.replace(/\/+$/, '') ?? '';
/** Every Engismart endpoint is under this one address (the backend has one module: /engismart/...). */
export const ENGISMART_BASE = `${API_ROOT}/engismart`;

export function isEngismartUrl(url: string): boolean {
  return url.startsWith(ENGISMART_BASE);
}
