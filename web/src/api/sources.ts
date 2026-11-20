import { request, API_BASE, ApiError, NetworkError, readableDetail } from './client';
import type { ApiMapping, IngestResult, Source } from './types';

/** Body for POST /api/sources (matches the existing SourceIn model). */
export interface SourceCreateInput {
  type: 'rss' | 'api';
  url: string;
  credibility: number;
  poll_interval: number;
  bubble_ids: string[];
  api_mapping?: ApiMapping | null;
  max_items_per_hour: number;
  store_full_text: boolean;
  enabled: boolean;
  /** RSS only. Not in SourceIn yet; flagged to the backend owner. */
  backfill_days?: number;
}

/** Body for PATCH /api/sources/{id} (matches SourcePatch). */
export interface SourcePatchInput {
  enabled?: boolean;
  credibility?: number;
  poll_interval?: number;
  bubble_ids?: string[];
  max_items_per_hour?: number;
  store_full_text?: boolean;
}

/** One item the "test" button would ingest. Nothing is stored. */
export interface TestedItem {
  title: string;
  url: string;
}

export interface SourceTestResult {
  items: TestedItem[];
}

export function listSources(signal?: AbortSignal): Promise<Source[]> {
  return request<Source[]>('GET', '/sources', undefined, signal);
}

export function createSource(input: SourceCreateInput): Promise<Source> {
  return request<Source>('POST', '/sources', input);
}

export function patchSource(id: string, input: SourcePatchInput): Promise<Source> {
  return request<Source>('PATCH', `/sources/${encodeURIComponent(id)}`, input);
}

export function deleteSource(id: string): Promise<void> {
  return request<void>('DELETE', `/sources/${encodeURIComponent(id)}`);
}

/** Fetches once and returns the first items, without storing them. */
export function testSource(input: SourceCreateInput): Promise<SourceTestResult> {
  return request<SourceTestResult>('POST', '/sources/test', input);
}

export interface UploadProgress {
  loaded: number;
  total: number;
}

export interface DocumentUploadInput {
  file: File;
  bubbleIds: string[];
  credibility: number;
  onProgress?: (p: UploadProgress) => void;
  signal?: AbortSignal;
}

/**
 * Uploads a document to POST /api/documents. XHR is used instead of fetch
 * because only XHR reports upload progress.
 */
export function uploadDocument(input: DocumentUploadInput): Promise<IngestResult[]> {
  return new Promise<IngestResult[]>((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open('POST', `${API_BASE}/documents`);
    xhr.setRequestHeader('Accept', 'application/json');
    xhr.upload.onprogress = (e: ProgressEvent) => {
      if (e.lengthComputable) input.onProgress?.({ loaded: e.loaded, total: e.total });
    };
    xhr.onerror = () => reject(new NetworkError());
    xhr.onabort = () => reject(new DOMException('Upload cancelled', 'AbortError'));
    xhr.onload = () => {
      let parsed: unknown = null;
      try {
        parsed = JSON.parse(xhr.responseText);
      } catch {
        parsed = null;
      }
      if (xhr.status >= 200 && xhr.status < 300) {
        resolve(parsed as IngestResult[]);
      } else {
        reject(new ApiError(xhr.status, readableDetail(parsed, `Upload failed (${xhr.status})`)));
      }
    };
    input.signal?.addEventListener('abort', () => xhr.abort(), { once: true });
    const form = new FormData();
    form.append('file', input.file, input.file.name);
    if (input.bubbleIds.length > 0) form.append('bubble_ids', input.bubbleIds.join(','));
    form.append('credibility', String(input.credibility));
    xhr.send(form);
  });
}
