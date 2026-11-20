import { request } from './client';
import type { Bubble } from './types';

export function listBubbles(signal?: AbortSignal): Promise<Bubble[]> {
  return request<Bubble[]>('GET', '/bubbles', undefined, signal);
}
