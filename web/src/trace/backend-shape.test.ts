import { describe, expect, it } from 'vitest';
import { BACKEND_AGENTIC_RUN, BACKEND_AGENTIC_STEPS, BACKEND_NORMAL_RUN, BACKEND_NORMAL_STEPS } from './fixtures/backend-runs';
import { buildSimpleView, relevanceOf, stepCount } from './model';
import type { Step } from './types';

// The trace must read what the real backend emits, not only the keys in types.ts.
describe('simple view on real backend steps', () => {
  it('normal run: every stage is done, and the search counts and relevance come from the backend keys', () => {
    const view = buildSimpleView(BACKEND_NORMAL_RUN, BACKEND_NORMAL_STEPS, { complete: true });
    expect(view.stages.map((s) => s.status)).toEqual(['done', 'done', 'done', 'done']);
    const gathered = view.stages[2]!;
    expect(gathered.items).toHaveLength(1);
    expect(gathered.items[0]?.count).toBe(1);
    // The backend's score step carries the relevance (1.0 here) and the retrieve step the count.
    expect(gathered.items[0]?.relevance).toBe(1);
    expect(view.stages[3]!.citations.map((c) => c.item_id)).toEqual(['i1']);
  });

  it('agentic run: one item per subagent, relevance taken from its child retrieve step', () => {
    const view = buildSimpleView(BACKEND_AGENTIC_RUN, BACKEND_AGENTIC_STEPS, { complete: true });
    expect(view.stages.map((s) => s.status)).toEqual(['done', 'done', 'done', 'done']);
    const items = view.stages[2]!.items;
    expect(items.map((i) => i.label)).toEqual(['news', 'finance']);
    expect(items.map((i) => i.relevance)).toEqual([1, 1]);
    expect(items.map((i) => i.count)).toEqual([1, 1]);
    expect(view.stages[1]!.bubbles).toEqual(['news', 'finance']);
  });

  it('a live run with no searches yet shows the search stage as waiting, not done', () => {
    const route = BACKEND_NORMAL_STEPS.slice(0, 1);
    const view = buildSimpleView({ mode: 'normal', status: 'running' }, route, { complete: false });
    expect(view.stages[0]!.status).toBe('done');
    expect(view.stages[1]!.status).toBe('pending');
  });
});

describe('summary keys from the backend', () => {
  it('counts facts plus chunks for a retrieve or subagent step', () => {
    expect(stepCount(BACKEND_NORMAL_STEPS[1]!)).toBe(1);
    expect(stepCount({ summary: { facts: 2, chunks: 3 }, node_ids: [] })).toBe(5);
  });

  it('takes relevance from score steps, and from the steps under a subagent', () => {
    const subagent = BACKEND_AGENTIC_STEPS.find((s) => s.kind === 'subagent') as Step;
    expect(relevanceOf(subagent, BACKEND_AGENTIC_STEPS)).toBe(1);
    const route = BACKEND_NORMAL_STEPS.find((s) => s.kind === 'route') as Step;
    expect(relevanceOf(route, BACKEND_NORMAL_STEPS)).toBeNull();
  });

  it('reads top_facts scores when a retrieve step has no score step', () => {
    const retrieve = {
      ...(BACKEND_NORMAL_STEPS.find((s) => s.kind === 'retrieve') as Step),
      summary: { top_facts: [{ id: 'a', score: 0.4 }, { id: 'b', score: 0.7 }] },
    } as Step;
    expect(relevanceOf(retrieve, [retrieve])).toBe(0.7);
  });
});
