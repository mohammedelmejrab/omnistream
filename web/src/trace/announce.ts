import type { Step } from './types';

// Screen-reader wording for live stages (spec 10.4). One announcement per
// stage change, not per event. Score steps stay silent.

function bubbleName(step: Step): string | null {
  return step.bubble && step.bubble.trim() ? step.bubble : null;
}

/** Plain-words label for a step that has started, or null when it stays silent. */
export function startLabel(step: Step): string | null {
  const b = bubbleName(step);
  switch (step.kind) {
    case 'route':
      return 'Understanding your question';
    case 'seed':
      return 'Choosing bubbles';
    case 'retrieve':
    case 'subagent':
      return b ? `Searching ${b} bubble` : 'Searching bubbles';
    case 'score':
      return null;
    case 'join':
      return 'Joining entities';
    case 'merge':
      return 'Merging evidence';
    case 'answer':
      return 'Writing answer';
  }
}

/** Failure wording, announced with role="alert". */
export function failureLabel(step: Step): string {
  const b = bubbleName(step);
  if (step.kind === 'subagent' || step.kind === 'retrieve') {
    return b ? `${b} bubble could not answer` : 'A bubble could not answer';
  }
  if (step.kind === 'answer') return 'The answer could not be written';
  return 'A step could not finish';
}

/**
 * Builds the polite announcement for a step. `position` is 1-based in the
 * ordered list; `total` is only passed once the run is finished, so a live
 * run never claims a final count it does not know.
 */
export function announceStep(
  step: Step,
  position: number,
  total: number | null,
): string | null {
  const label = startLabel(step);
  if (!label) return null;
  const of = total !== null ? ` of ${total}` : '';
  return `${label}, step ${position}${of}`;
}

/**
 * Keeps the last announced label so repeated steps for the same bubble
 * (retrieve, then subagent) are read once.
 */
export function dedupeAnnouncement(lastLabel: string | null, next: string | null): {
  announce: string | null;
  last: string | null;
} {
  if (!next) return { announce: null, last: lastLabel };
  const bare = next.replace(/, step .*$/, '');
  if (bare === lastLabel) return { announce: null, last: lastLabel };
  return { announce: next, last: bare };
}
