// Thin fetch wrapper for the JSON API. Relative URLs only, so the same code
// works behind the Vite proxy in development and on the FastAPI origin.

export class ApiError extends Error {
  readonly status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
  }
}

/** The server could not be reached at all (offline or server down). */
export class NetworkError extends Error {
  constructor(message = 'OmniStream server is unreachable') {
    super(message);
    this.name = 'NetworkError';
  }
}

export const API_BASE = '/api';

/** Turns FastAPI error bodies ({detail: string | [{msg}]}) into readable text. */
export function readableDetail(body: unknown, fallback: string): string {
  if (body && typeof body === 'object' && 'detail' in body) {
    const detail = (body as { detail: unknown }).detail;
    if (typeof detail === 'string' && detail.trim()) return detail;
    if (Array.isArray(detail)) {
      const msgs = detail
        .map((d) => (d && typeof d === 'object' && 'msg' in d ? String((d as { msg: unknown }).msg) : ''))
        .filter(Boolean);
      if (msgs.length > 0) return msgs.join('; ');
    }
  }
  return fallback;
}

export async function request<T>(
  method: 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE',
  path: string,
  body?: unknown,
  signal?: AbortSignal,
): Promise<T> {
  const init: RequestInit = { method, headers: { Accept: 'application/json' } };
  if (signal) init.signal = signal;
  if (body !== undefined) {
    init.headers = { Accept: 'application/json', 'Content-Type': 'application/json' };
    init.body = JSON.stringify(body);
  }
  let res: Response;
  try {
    res = await fetch(`${API_BASE}${path}`, init);
  } catch (err) {
    if (err instanceof DOMException && err.name === 'AbortError') throw err;
    throw new NetworkError();
  }
  if (res.status === 204) return undefined as T;
  const text = await res.text();
  let parsed: unknown = null;
  if (text) {
    try {
      parsed = JSON.parse(text);
    } catch {
      parsed = null;
    }
  }
  if (!res.ok) {
    throw new ApiError(res.status, readableDetail(parsed, `Request failed (${res.status})`));
  }
  return parsed as T;
}

export function isNotFound(err: unknown): boolean {
  return err instanceof ApiError && err.status === 404;
}

/** Readable text for any thrown value. Never includes request bodies or keys. */
export function messageOf(err: unknown): string {
  if (err instanceof NetworkError) return 'OmniStream server is unreachable. Check that it is running.';
  if (err instanceof ApiError) return err.message;
  if (err instanceof Error) return err.message;
  return 'Something went wrong.';
}
