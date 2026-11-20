import { describe, expect, it } from 'vitest';
import type { Step } from '@/api/types';
import { currentStep, describeStep } from './announce';

const step = (over: Partial<Step>): Step => ({
  id: 's',
  run_id: 'r',
  parent_step_id: null,
  kind: 'route',
  bubble: null,
  started_at: '2026-11-18T09:00:00Z',
  duration_ms: null,
  status: 'ok',
  summary: {},
  node_ids: [],
  edge_ids: [],
  citations: [],
  error: null,
  ...over,
});

const names = (id: string): string | null => (id === 'b1' ? 'Energy' : null);

describe('live stage announcements', () => {
  it('says what is happening in words, with a step number', () => {
    expect(describeStep(step({ kind: 'retrieve', bubble: 'b1' }), names, 3)).toBe(
      'Searching Energy bubble, step 3',
    );
  });

  it('reports a failed subagent in plain text', () => {
    expect(describeStep(step({ kind: 'subagent', bubble: 'b1', status: 'error' }), names)).toBe(
      'Energy bubble could not answer',
    );
  });

  it('falls back to a generic bubble name when the bubble is unknown', () => {
    expect(describeStep(step({ kind: 'score', bubble: 'zz' }), names)).toBe('Scoring evidence from bubbles');
  });

  it('prefers a running step as the current stage', () => {
    const steps = [step({ id: 'a', kind: 'route' }), step({ id: 'b', kind: 'retrieve', status: 'running' })];
    expect(currentStep(steps)?.id).toBe('b');
  });
});
