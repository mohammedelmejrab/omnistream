import { vi } from 'vitest';

export interface MockReply {
  status?: number;
  json?: unknown;
}

export type MockHandler = (call: { method: string; path: string; body: unknown }) => MockReply | Promise<MockReply>;

export interface ApiMock {
  calls: { method: string; path: string; body: unknown }[];
}

/**
 * Replaces global fetch with a handler keyed by method and API path
 * (without the /api prefix). Unhandled routes answer 500 so tests fail loudly.
 */
export function mockApi(handler: MockHandler): ApiMock {
  const mock: ApiMock = { calls: [] };
  vi.stubGlobal(
    'fetch',
    vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url;
      const path = url.replace(/^.*\/api/, '');
      const method = (init?.method ?? 'GET').toUpperCase();
      const body = typeof init?.body === 'string' ? (JSON.parse(init.body) as unknown) : undefined;
      mock.calls.push({ method, path, body });
      const reply = await handler({ method, path, body });
      const status = reply.status ?? 200;
      const text = reply.json === undefined ? '' : JSON.stringify(reply.json);
      return new Response(text, { status, headers: { 'content-type': 'application/json' } });
    }),
  );
  return mock;
}

export function iso(offsetSeconds = 0): string {
  return new Date(Date.UTC(2026, 10, 18, 9, 0, offsetSeconds)).toISOString();
}
