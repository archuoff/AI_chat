import { environment } from '../../../environments/environment';

/** The platform API address the two Engismart modules hang under, e.g. https://host/engismart/api/v1 (set in the environment files). */
export const API_ROOT: string = ((environment as Record<string, unknown>)['engismartUrl'] as string | undefined)?.replace(/\/+$/, '') ?? '';
/** chat: me, health, domains, chat, picture files (application alias engismart_chat) */
export const CHAT_BASE = `${API_ROOT}/engismart_chat`;
/** ingestion: documents, pictures management, search, users, usage (application alias engismart_ingestion, developers) */
export const INGESTION_BASE = `${API_ROOT}/engismart_ingestion`;

/** Which module serves a path (the paths are the ones in docs/API.md). */
export function baseOf(path: string): string {
  const chat = /^\/(me|health|domains|warmup|chat)(\/|$)/.test(path) || /^\/images\/[^/]+\/file$/.test(path);
  return chat ? CHAT_BASE : INGESTION_BASE;
}

export function isEngismartUrl(url: string): boolean {
  return url.startsWith(CHAT_BASE) || url.startsWith(INGESTION_BASE);
}
