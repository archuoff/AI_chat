import { environment } from '../../../environments/environment';

/** Where the Engismart backend lives, e.g. https://host/engismart/api/v1/engismart (set in the environment files). */
export const API_BASE: string = ((environment as Record<string, unknown>)['engismartUrl'] as string | undefined)?.replace(/\/+$/, '') ?? '/engismart';
