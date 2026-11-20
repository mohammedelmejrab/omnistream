import type { Source } from '@/api/types';

export const DOCUMENT_EXTENSIONS = ['.pdf', '.docx', '.txt', '.md'] as const;

/** Canonical form used to detect duplicate sources (spec 8, "Already added"). */
export function normalizeUrl(raw: string): string | null {
  const trimmed = raw.trim();
  if (!trimmed) return null;
  let url: URL;
  try {
    url = new URL(trimmed);
  } catch {
    return null;
  }
  if (url.protocol !== 'http:' && url.protocol !== 'https:') return null;
  if (!url.hostname) return null;
  url.hash = '';
  url.hostname = url.hostname.toLowerCase();
  const path = url.pathname.replace(/\/+$/, '');
  return `${url.protocol}//${url.host}${path}${url.search}`;
}

export function isValidHttpUrl(raw: string): boolean {
  return normalizeUrl(raw) !== null;
}

export function findDuplicateSource(sources: readonly Source[], rawUrl: string, ignoreId?: string): Source | undefined {
  const target = normalizeUrl(rawUrl);
  if (!target) return undefined;
  return sources.find((s) => s.id !== ignoreId && s.url !== null && normalizeUrl(s.url) === target);
}

export type DocumentCheck = { ok: true } | { ok: false; message: string };

export function checkDocumentFile(file: { name: string }): DocumentCheck {
  const dot = file.name.lastIndexOf('.');
  const ext = dot >= 0 ? file.name.slice(dot).toLowerCase() : '';
  if (!(DOCUMENT_EXTENSIONS as readonly string[]).includes(ext)) {
    return {
      ok: false,
      message: `"${file.name}" is not a supported file. Use .pdf, .docx, .txt or .md.`,
    };
  }
  return { ok: true };
}

/** Maps the server's upload error (status and detail) to a clear message. */
export function uploadErrorMessage(status: number, detail: string): string {
  if (status === 413) return 'This file is over the size limit set for this server.';
  if (status === 415) return detail || 'This file type is not supported.';
  if (status === 422) return `The file could not be read. ${detail}`.trim();
  return detail || 'The upload failed.';
}

export function parseCredibility(raw: string): number | null {
  if (raw.trim() === '') return null;
  const n = Number(raw);
  if (!Number.isFinite(n) || n < 0 || n > 1) return null;
  return n;
}

export function parsePositiveInt(raw: string): number | null {
  if (raw.trim() === '') return null;
  const n = Number(raw);
  if (!Number.isInteger(n) || n < 1) return null;
  return n;
}
