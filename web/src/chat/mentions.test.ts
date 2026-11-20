import { describe, expect, it } from 'vitest';
import type { Bubble, Source } from '@/api/types';
import { MAX_QUESTION_CHARS, buildOptions, filterOptions, findMentionQuery, resolveScope } from './mentions';

const now = '2026-11-18T09:00:00Z';
const bubble = (id: string, name: string): Bubble => ({
  id,
  name,
  description: '',
  half_life_days: 30,
  created_at: now,
  updated_at: now,
});
const source = (id: string, bubbleIds: string[]): Source => ({
  id,
  type: 'rss',
  url: `https://example.com/${id}`,
  credibility: 0.5,
  poll_interval: 900,
  bubble_ids: bubbleIds,
  api_mapping: null,
  max_items_per_hour: 30,
  store_full_text: true,
  enabled: true,
  last_polled_at: null,
  status: 'ok',
  last_error: null,
});

describe('mention query', () => {
  it('finds an @token that ends at the caret and starts a word', () => {
    expect(findMentionQuery('ask @ene', 8)).toEqual({ start: 4, query: 'ene' });
    expect(findMentionQuery('@', 1)).toEqual({ start: 0, query: '' });
  });

  it('ignores @ inside a word such as an email address', () => {
    expect(findMentionQuery('mail a@b', 8)).toBeNull();
  });

  it('ignores a token that is already closed by a space', () => {
    expect(findMentionQuery('@energy now', 11)).toBeNull();
  });

  it('filters options by label or detail, case-insensitively', () => {
    const options = buildOptions([bubble('b1', 'Energy'), bubble('b2', 'Health')], [source('s1', ['b1'])]);
    expect(filterOptions(options, 'ENER').map((o) => o.id)).toEqual(['b1']);
    expect(filterOptions(options, 'rss').length).toBe(1);
  });
});

describe('scope resolution', () => {
  const bubbles = [bubble('b1', 'Energy'), bubble('b2', 'Health')];

  it('sends no restriction when nothing is selected', () => {
    expect(resolveScope([], bubbles, [])).toEqual({ bubbleIds: undefined, missing: [], blocked: false });
  });

  it('expands a source into its bubbles', () => {
    const scope = resolveScope(
      [{ kind: 'source', id: 's1', label: 'feed' }],
      bubbles,
      [source('s1', ['b1', 'b2'])],
    );
    expect(scope.bubbleIds).toEqual(['b1', 'b2']);
  });

  it('never sends a bubble deleted after being typed', () => {
    const scope = resolveScope(
      [
        { kind: 'bubble', id: 'b1', label: 'Energy' },
        { kind: 'bubble', id: 'gone', label: 'Old' },
      ],
      bubbles,
      [],
    );
    expect(scope.bubbleIds).toEqual(['b1']);
    expect(scope.missing.map((m) => m.id)).toEqual(['gone']);
  });

  it('blocks when every selected item is gone', () => {
    const scope = resolveScope([{ kind: 'bubble', id: 'gone', label: 'Old' }], bubbles, []);
    expect(scope.blocked).toBe(true);
  });

  it('keeps the 20,000 character limit that matches POST /query', () => {
    expect(MAX_QUESTION_CHARS).toBe(20_000);
  });
});
