import { request } from './client';
import type { ProviderInput, ProviderSettings, ProviderTestResult } from './types';

export function getProvider(signal?: AbortSignal): Promise<ProviderSettings> {
  return request<ProviderSettings>('GET', '/settings/provider', undefined, signal);
}

export function saveProvider(input: ProviderInput): Promise<ProviderSettings> {
  return request<ProviderSettings>('PUT', '/settings/provider', input);
}

export function clearProviderKey(): Promise<ProviderSettings> {
  return request<ProviderSettings>('DELETE', '/settings/provider/key');
}

export function testProvider(): Promise<ProviderTestResult> {
  return request<ProviderTestResult>('POST', '/settings/provider/test');
}
