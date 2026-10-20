import type { components } from './api-types';
import { supabase } from './supabase';

// Types come from api-types.ts, generated from the backend (`npm run api-types`).
export type Schemas = components['schemas'];

export const apiUrl = (process.env.EXPO_PUBLIC_API_URL ?? 'http://localhost:8000').replace(/\/+$/, '');

// Without "https://" the browser treats the address as a page on this website.
if (!/^https?:\/\//.test(apiUrl)) {
  throw new Error(
    `EXPO_PUBLIC_API_URL must start with http:// or https:// (got "${apiUrl}"). Fix it in frontend/.env or the Vercel project settings.`,
  );
}

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
    // The API's error details, e.g. { missing: [...] } for incomplete onboarding.
    public detail?: unknown,
  ) {
    super(message);
  }
}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const { data } = await supabase.auth.getSession();
  const token = data.session?.access_token;
  const headers: Record<string, string> = token ? { Authorization: `Bearer ${token}` } : {};
  if (body !== undefined) headers['Content-Type'] = 'application/json';

  let response: Response;
  try {
    response = await fetch(`${apiUrl}${path}`, {
      method,
      headers,
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });
  } catch {
    throw new ApiError(0, 'Can’t reach the server. Is the backend running?');
  }
  if (!response.ok) {
    const detail = await response
      .json()
      .then((json) => json.detail)
      .catch(() => undefined);
    const message =
      response.status === 422 ? 'Some values aren’t valid.' : `Request failed (${response.status})`;
    throw new ApiError(response.status, message, detail);
  }
  try {
    return (await response.json()) as T;
  } catch {
    // e.g. the address points at a website instead of the API, which answers with HTML.
    throw new ApiError(response.status, 'The server sent an unexpected reply. Check the API address.');
  }
}

// Calls our backend API as the signed-in person.
export function apiGet<T>(path: string): Promise<T> {
  return request<T>('GET', path);
}

export function apiPatch<T>(path: string, body: unknown): Promise<T> {
  return request<T>('PATCH', path, body);
}

export function apiDelete<T>(path: string): Promise<T> {
  return request<T>('DELETE', path);
}

export function apiPut<T>(path: string, body: unknown): Promise<T> {
  return request<T>('PUT', path, body);
}

export function apiPost<T>(path: string, body?: unknown): Promise<T> {
  return request<T>('POST', path, body);
}
