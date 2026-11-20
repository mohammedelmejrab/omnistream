import type { Bubble, Source } from '@/api/types';
import type { StatusTone } from '@/components/StatusChip';

export interface SourceStatus {
  tone: StatusTone;
  label: string;
}

/** Status is always shown with an icon and a word (spec 8, 11). */
export function sourceStatus(source: Source, bubbleIds: ReadonlySet<string>): SourceStatus {
  if (!source.enabled) return { tone: 'muted', label: 'Disabled' };
  if (!hasLiveBubble(source, bubbleIds)) return { tone: 'muted', label: 'No bubble' };
  if (source.status === 'error') return { tone: 'error', label: 'Error' };
  if (source.status === 'ok') return { tone: 'ok', label: 'OK' };
  return { tone: 'muted', label: 'Pending' };
}

/** A source whose bubbles were all deleted is "no bubble" and does not poll. Document sources without bubbles stay live. */
export function hasLiveBubble(source: Source, bubbleIds: ReadonlySet<string>): boolean {
  if (source.type === 'document' && source.bubble_ids.length === 0) return true;
  return source.bubble_ids.some((id) => bubbleIds.has(id));
}

export interface SourceGroup {
  key: string;
  title: string;
  sources: Source[];
}

/**
 * Groups sources under the first bubble they live in. Sources with no live
 * bubble go in "No bubble", last (spec 8, grouped by bubble).
 */
export function groupByBubble(sources: readonly Source[], bubbles: readonly Bubble[]): SourceGroup[] {
  const names = new Map(bubbles.map((b) => [b.id, b.name] as const));
  const groups = new Map<string, SourceGroup>();
  const orphan: Source[] = [];
  for (const s of sources) {
    const live = s.bubble_ids.find((id) => names.has(id));
    if (!live) {
      orphan.push(s);
      continue;
    }
    const existing = groups.get(live);
    if (existing) existing.sources.push(s);
    else groups.set(live, { key: live, title: names.get(live) ?? live, sources: [s] });
  }
  const ordered = [...groups.values()].sort((a, b) => a.title.localeCompare(b.title));
  if (orphan.length > 0) ordered.push({ key: 'none', title: 'No bubble', sources: orphan });
  return ordered;
}

export function formatWhen(iso: string | null): string {
  if (!iso) return 'Never';
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? 'Unknown' : d.toLocaleString();
}

export const POLL_OPTIONS: readonly { value: number; label: string }[] = [
  { value: 900, label: 'Every 15 minutes' },
  { value: 3600, label: 'Every hour' },
  { value: 21600, label: 'Every 6 hours' },
  { value: 86400, label: 'Every day' },
];
