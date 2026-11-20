import { describe, expect, it } from 'vitest';
import type { Source } from '@/api/types';
import {
  checkDocumentFile,
  findDuplicateSource,
  isValidHttpUrl,
  normalizeUrl,
  parseCredibility,
  parsePositiveInt,
  uploadErrorMessage,
} from './validation';
import { groupByBubble, sourceStatus } from './sourceStatus';

const base: Source = {
  id: 's1',
  type: 'rss',
  url: 'https://Example.com/feed/',
  credibility: 0.5,
  poll_interval: 900,
  bubble_ids: ['b1'],
  api_mapping: null,
  max_items_per_hour: 30,
  store_full_text: true,
  enabled: true,
  last_polled_at: null,
  status: 'ok',
  last_error: null,
};

describe('URL validation', () => {
  it('accepts only http and https addresses', () => {
    expect(isValidHttpUrl('https://example.com/a')).toBe(true);
    expect(isValidHttpUrl('ftp://example.com')).toBe(false);
    expect(isValidHttpUrl('example.com')).toBe(false);
    expect(isValidHttpUrl('   ')).toBe(false);
  });

  it('normalises case, trailing slashes and fragments for duplicate checks', () => {
    expect(normalizeUrl('HTTPS://Example.com/feed/#top')).toBe('https://example.com/feed');
  });

  it('finds an existing source with the same address', () => {
    expect(findDuplicateSource([base], 'https://example.com/feed')?.id).toBe('s1');
    expect(findDuplicateSource([base], 'https://example.com/other')).toBeUndefined();
  });
});

describe('document checks', () => {
  it('accepts the formats sources/documents.py accepts, in any case', () => {
    expect(checkDocumentFile({ name: 'Report.PDF' }).ok).toBe(true);
    expect(checkDocumentFile({ name: 'notes.md' }).ok).toBe(true);
  });

  it('rejects an unsupported file with a clear message', () => {
    const check = checkDocumentFile({ name: 'slides.pptx' });
    expect(check.ok).toBe(false);
    if (!check.ok) expect(check.message).toContain('.pdf, .docx, .txt or .md');
  });

  it('maps size and parse failures to their own messages', () => {
    expect(uploadErrorMessage(413, '')).toMatch(/size limit/);
    expect(uploadErrorMessage(422, 'bad pdf')).toMatch(/could not be read/);
  });
});

describe('numeric fields', () => {
  it('keeps credibility within 0 to 1', () => {
    expect(parseCredibility('0.5')).toBe(0.5);
    expect(parseCredibility('1.2')).toBeNull();
    expect(parseCredibility('')).toBeNull();
  });

  it('requires whole positive numbers for rate and backfill', () => {
    expect(parsePositiveInt('30')).toBe(30);
    expect(parsePositiveInt('0')).toBeNull();
    expect(parsePositiveInt('2.5')).toBeNull();
  });
});

describe('status and grouping', () => {
  const bubbles = [
    { id: 'b1', name: 'Energy', description: '', half_life_days: 30, created_at: '', updated_at: '' },
  ];

  it('marks a source whose bubble was deleted as "No bubble"', () => {
    const orphan = { ...base, bubble_ids: ['gone'] };
    expect(sourceStatus(orphan, new Set(['b1']))).toEqual({ tone: 'muted', label: 'No bubble' });
  });

  it('shows status with a word, not colour alone', () => {
    expect(sourceStatus({ ...base, status: 'error' }, new Set(['b1'])).label).toBe('Error');
    expect(sourceStatus({ ...base, enabled: false }, new Set(['b1'])).label).toBe('Disabled');
  });

  it('groups by bubble and puts orphans last', () => {
    const groups = groupByBubble([base, { ...base, id: 's2', bubble_ids: ['gone'] }], bubbles);
    expect(groups.map((g) => g.title)).toEqual(['Energy', 'No bubble']);
  });
});
