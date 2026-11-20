import type { Bubble, Source } from '@/api/types';

export const MAX_QUESTION_CHARS = 20_000;
/** Show the counter once the question is this close to the limit. */
export const COUNTER_THRESHOLD = 18_000;

export interface Mention {
  kind: 'bubble' | 'source';
  id: string;
  label: string;
}

export interface MentionOption extends Mention {
  detail: string;
}

export interface MentionQuery {
  /** Index of the "@" character in the text. */
  start: number;
  query: string;
}

/** Finds an "@token" that ends at the caret and starts a word. */
export function findMentionQuery(text: string, caret: number): MentionQuery | null {
  const before = text.slice(0, caret);
  const match = /(^|\s)@([^\s@]*)$/.exec(before);
  if (!match) return null;
  const query = match[2] ?? '';
  return { start: before.length - query.length - 1, query };
}

export function sourceLabel(source: Source): string {
  if (source.url) return source.url;
  return source.type === 'document' ? 'Uploaded document' : `${source.type} source`;
}

export function sourceTypeLabel(type: Source['type']): string {
  switch (type) {
    case 'rss':
      return 'RSS feed';
    case 'api':
      return 'API';
    case 'document':
      return 'Document';
    default:
      return 'Source';
  }
}

export function buildOptions(bubbles: readonly Bubble[], sources: readonly Source[]): MentionOption[] {
  const bubbleOptions: MentionOption[] = bubbles.map((b) => ({
    kind: 'bubble',
    id: b.id,
    label: b.name,
    detail: 'Bubble',
  }));
  const sourceOptions: MentionOption[] = sources.map((s) => ({
    kind: 'source',
    id: s.id,
    label: sourceLabel(s),
    detail: `${sourceTypeLabel(s.type)} source`,
  }));
  return [...bubbleOptions, ...sourceOptions];
}

export function filterOptions(options: readonly MentionOption[], query: string, limit = 8): MentionOption[] {
  const q = query.trim().toLowerCase();
  const matches = q
    ? options.filter((o) => o.label.toLowerCase().includes(q) || o.detail.toLowerCase().includes(q))
    : options;
  return matches.slice(0, limit);
}

export interface ResolvedScope {
  /** Bubble ids to send. Undefined means "every bubble". */
  bubbleIds: string[] | undefined;
  /** Mentions whose bubble or source no longer exists. Never sent. */
  missing: Mention[];
  /** True when mentions were typed but none of them resolve to a bubble. */
  blocked: boolean;
}

/**
 * Turns selected mentions into bubble ids. A source contributes its bubbles.
 * Mentions to deleted bubbles or sources are reported as missing (spec 6).
 */
export function resolveScope(
  mentions: readonly Mention[],
  bubbles: readonly Bubble[],
  sources: readonly Source[],
): ResolvedScope {
  if (mentions.length === 0) return { bubbleIds: undefined, missing: [], blocked: false };
  const bubbleIds = new Set(bubbles.map((b) => b.id));
  const sourceById = new Map(sources.map((s) => [s.id, s] as const));
  const ids = new Set<string>();
  const missing: Mention[] = [];
  for (const m of mentions) {
    if (m.kind === 'bubble') {
      if (bubbleIds.has(m.id)) ids.add(m.id);
      else missing.push(m);
    } else {
      const source = sourceById.get(m.id);
      if (!source) {
        missing.push(m);
        continue;
      }
      const live = source.bubble_ids.filter((id) => bubbleIds.has(id));
      if (live.length === 0) missing.push(m);
      live.forEach((id) => ids.add(id));
    }
  }
  return { bubbleIds: [...ids], missing, blocked: ids.size === 0 };
}
