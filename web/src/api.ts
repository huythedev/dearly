import type { Command, Envelope } from './types';

export class APIError extends Error {
  constructor(public status: number, message: string) { super(message); }
}
export const language = () => localStorage.getItem('dearly.language') === 'vi' ? 'vi' : 'en';

export async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const headers = new Headers(options.headers);
  headers.set('Accept', 'application/json');
  headers.set('Accept-Language', language());
  headers.set('X-Dearly-Client', 'web');
  if (options.body) headers.set('Content-Type', 'application/json');
  const response = await fetch(`/v1/${path}`, {
    ...options, headers, credentials: 'same-origin', cache: 'no-store', redirect: 'error',
    signal: options.signal ?? AbortSignal.timeout(15000),
  });
  if (response.status === 304) return null as T;
  const data = await response.json();
  if (!response.ok) throw new APIError(response.status, data.detail ?? 'The server could not complete your request.');
  return data as T;
}

export async function fetchState(etag: string | null): Promise<{ envelope: Envelope | null; etag: string | null }> {
  const response = await fetch('/v1/state', {
    headers: { 'Accept-Language': language(), ...(etag ? { 'If-None-Match': etag } : {}) },
    credentials: 'same-origin', cache: 'no-store', redirect: 'error', signal: AbortSignal.timeout(15000),
  });
  if (response.status === 304) return { envelope: null, etag };
  const data = await response.json();
  if (!response.ok) throw new APIError(response.status, data.detail ?? 'Could not sync.');
  return { envelope: data, etag: response.headers.get('ETag') };
}

export function command(kind: string, payload: Record<string, unknown>): Command {
  // getRandomValues also works on a trusted HTTP LAN during local development.
  const bytes = crypto.getRandomValues(new Uint8Array(16));
  bytes[6] = (bytes[6] & 15) | 64; bytes[8] = (bytes[8] & 63) | 128;
  const hex = Array.from(bytes, value => value.toString(16).padStart(2, '0')).join('');
  const requestID = `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
  return { requestID, kind, payload };
}

export async function sendCommand(value: Command): Promise<{ ok: boolean; id?: string }> {
  const body = JSON.stringify(value);
  try { return await request('actions', { method: 'POST', body }); }
  catch (error) {
    if (error instanceof APIError && error.status !== 503) throw error;
    // A lost reply may already be committed. Reuse the exact idempotency key and body.
    return request('actions', { method: 'POST', body });
  }
}
