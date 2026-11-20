import { request } from './client';
import type { GraphResponse } from './types';

export interface GraphQuery {
  bubble?: string;
  limit?: number;
  offset?: number;
}

export function getGraph(query: GraphQuery = {}, signal?: AbortSignal): Promise<GraphResponse> {
  const params = new URLSearchParams();
  if (query.bubble) params.set('bubble', query.bubble);
  params.set('limit', String(query.limit ?? 300));
  params.set('offset', String(query.offset ?? 0));
  return request<GraphResponse>('GET', `/graph?${params.toString()}`, undefined, signal);
}
