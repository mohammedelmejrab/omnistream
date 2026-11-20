import { request } from './client';
import type { Run, Step } from './types';

export function getRun(id: string, signal?: AbortSignal): Promise<Run> {
  return request<Run>('GET', `/runs/${encodeURIComponent(id)}`, undefined, signal);
}

export function getRunSteps(id: string, signal?: AbortSignal): Promise<Step[]> {
  return request<Step[]>('GET', `/runs/${encodeURIComponent(id)}/steps`, undefined, signal);
}

export function cancelRun(id: string): Promise<Run> {
  return request<Run>('POST', `/runs/${encodeURIComponent(id)}/cancel`);
}
