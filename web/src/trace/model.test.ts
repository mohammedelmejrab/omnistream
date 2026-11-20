import { describe, expect, it } from 'vitest';
import { AGENTIC_RUN, AGENTIC_STEPS, NORMAL_RUN, NORMAL_STEPS } from './fixtures/stored-runs';
import {
  buildSimpleView,
  citationNumber,
  currentStageIndex,
  failureText,
  mergeStep,
  mergeSteps,
  orderSteps,
  relevanceBand,
  stepLabels,
  stepRelevance,
} from './model';
import type { Step } from './types';

const stage = (view: ReturnType<typeof buildSimpleView>, key: string) => {
  const s = view.stages.find((x) => x.key === key);
  if (!s) throw new Error(`no stage ${key}`);
  return s;
};

describe('orderSteps and mergeStep', () => {
  it('orders by start time, then pipeline stage', () => {
    const shuffled = [...NORMAL_STEPS].reverse();
    expect(orderSteps(shuffled).map((s) => s.id)).toEqual(NORMAL_STEPS.map((s) => s.id));
  });

  it('upserts a step by id (start event, then finish event)', () => {
    const started: Step = { ...NORMAL_STEPS[2]!, status: 'running', duration_ms: null };
    const steps = mergeStep([NORMAL_STEPS[0]!], started);
    expect(steps).toHaveLength(2);
    const finished = mergeStep(steps, NORMAL_STEPS[2]!);
    expect(finished).toHaveLength(2);
    expect(finished.find((s) => s.id === 'n-retrieve')?.status).toBe('ok');
  });

  it('never moves a finished step back to running (late catch-up copy)', () => {
    const done = NORMAL_STEPS[2]!;
    const late = { ...done, status: 'running' as const, duration_ms: null };
    const steps = mergeStep([done], late);
    expect(steps[0]?.status).toBe('ok');
  });

  it('mergeSteps applies every incoming step', () => {
    const merged = mergeSteps([], NORMAL_STEPS);
    expect(merged.map((s) => s.id)).toEqual(NORMAL_STEPS.map((s) => s.id));
  });
});

describe('relevance', () => {
  it('bands Low / Medium / High', () => {
    expect(relevanceBand(0.1)).toBe('Low');
    expect(relevanceBand(0.5)).toBe('Medium');
    expect(relevanceBand(0.66)).toBe('High');
    expect(relevanceBand(1)).toBe('High');
  });

  it('reads relevance from the summary and ignores missing values', () => {
    expect(stepRelevance(AGENTIC_STEPS[2]!)).toBe(0.82);
    expect(stepRelevance(AGENTIC_STEPS[4]!)).toBeNull();
  });
});

describe('buildSimpleView, normal run', () => {
  const view = buildSimpleView(NORMAL_RUN, NORMAL_STEPS, { complete: true });

  it('shows the four stages in order', () => {
    expect(view.stages.map((s) => s.key)).toEqual(['understood', 'searched', 'gathered', 'wrote']);
    expect(view.stages.map((s) => s.title)).toEqual([
      'Understood your question',
      'Searched bubbles',
      'Gathered evidence',
      'Wrote answer',
    ]);
  });

  it('reports every stage as done', () => {
    expect(view.stages.map((s) => s.status)).toEqual(['done', 'done', 'done', 'done']);
  });

  it('lists the bubbles as chips', () => {
    expect(stage(view, 'searched').bubbles).toEqual(['Energy']);
  });

  it('gives Normal one evidence total, with relevance from the score step', () => {
    const gathered = stage(view, 'gathered');
    expect(gathered.items).toHaveLength(1);
    expect(gathered.items[0]).toMatchObject({ count: 4, relevance: 0.5 });
  });

  it('shows the cited sources on the answer stage', () => {
    expect(stage(view, 'wrote').citations.map((c) => c.item_id)).toEqual(['item-gas-1']);
    expect(citationNumber(stage(view, 'wrote').citations, 'item-gas-1')).toBe(1);
  });

  it('highlights the answer when present', () => {
    expect(view.highlightAnswer).toBe(true);
  });
});

describe('buildSimpleView, agentic run with a failed bubble', () => {
  const view = buildSimpleView(AGENTIC_RUN, AGENTIC_STEPS, { complete: true });

  it('gives one evidence item per bubble subagent', () => {
    const items = stage(view, 'gathered').items;
    expect(items.map((i) => i.label)).toEqual(['Energy', 'Policy']);
  });

  it('marks the failed bubble and keeps the stage done for the rest', () => {
    const gathered = stage(view, 'gathered');
    expect(gathered.items[1]?.status).toBe('error');
    expect(gathered.items[1]?.error).toBe('Provider timeout after 30s');
    expect(gathered.status).toBe('done');
  });

  it('the answer still shows and cites the source that worked', () => {
    expect(stage(view, 'wrote').status).toBe('done');
    expect(stage(view, 'wrote').citations).toHaveLength(1);
  });

  it('lists both bubbles in the searched stage', () => {
    expect(stage(view, 'searched').bubbles).toEqual(['Energy', 'Policy']);
  });
});

describe('buildSimpleView, edge cases', () => {
  it('says "No relevant sources" when retrieval found nothing', () => {
    const steps = NORMAL_STEPS.map((s) =>
      s.kind === 'retrieve' ? { ...s, summary: { count: 0 }, node_ids: [] } : s,
    );
    const view = buildSimpleView(NORMAL_RUN, steps, { complete: true });
    expect(stage(view, 'gathered').status).toBe('no-evidence');
    expect(stage(view, 'gathered').noEvidence).toBe(true);
  });

  it('a failed run with no answer shows the wrote stage as could not finish', () => {
    const steps = NORMAL_STEPS.filter((s) => s.kind !== 'answer');
    const run = { ...NORMAL_RUN, status: 'failed' as const, answer: null, error: 'Rate limited' };
    const view = buildSimpleView(run, steps, { complete: true });
    expect(stage(view, 'wrote').status).toBe('failed');
    expect(view.highlightAnswer).toBe(false);
  });

  it('a partial replay prefix leaves unrevealed stages waiting, not failed', () => {
    const view = buildSimpleView(NORMAL_RUN, NORMAL_STEPS.slice(0, 2), { complete: false });
    expect(stage(view, 'understood').status).toBe('done');
    expect(stage(view, 'gathered').status).toBe('pending');
    expect(stage(view, 'wrote').status).toBe('pending');
  });

  it('a running step makes its stage working', () => {
    const steps = NORMAL_STEPS.map((s) =>
      s.kind === 'retrieve' ? { ...s, status: 'running' as const, duration_ms: null } : s,
    );
    const view = buildSimpleView({ ...NORMAL_RUN, status: 'running' }, steps, { complete: false });
    expect(stage(view, 'gathered').status).toBe('working');
  });

  it('currentStageIndex follows the replay cursor', () => {
    const view = buildSimpleView(NORMAL_RUN, NORMAL_STEPS, { complete: true });
    // Steps: route(0) seed(1) retrieve(2) score(3) answer(4)
    expect(currentStageIndex(view, 0)).toBe(-1);
    expect(currentStageIndex(view, 1)).toBe(0); // route revealed
    expect(currentStageIndex(view, 2)).toBe(1); // seed revealed
    expect(currentStageIndex(view, 3)).toBe(2); // retrieve revealed
    expect(currentStageIndex(view, 5)).toBe(3); // answer revealed
  });
});

describe('failureText', () => {
  it('uses plain words for each non-ok run status', () => {
    expect(failureText({ status: 'cancelled', error: null })).toBe('Stopped');
    expect(failureText({ status: 'interrupted', error: null })).toBe(
      'Interrupted when OmniStream restarted',
    );
    expect(failureText({ status: 'failed', error: 'bad key' })).toBe('bad key');
    expect(failureText({ status: 'ok', error: null })).toBeNull();
  });
});

describe('stepLabels', () => {
  const step = (id: string, kind: Step['kind'], over: Partial<Step> = {}): Step =>
    ({
      id,
      run_id: 'r',
      seq: 0,
      parent_step_id: null,
      kind,
      bubble: null,
      started_at: '2026-11-18T02:00:00.000Z',
      duration_ms: 1,
      status: 'ok',
      summary: {},
      node_ids: [],
      edge_ids: [],
      citations: [],
      error: null,
      ...over,
    }) as Step;

  it('names seed and score steps by the bubble of their nearest ancestor', () => {
    const steps = [
      step('sub-news', 'subagent', { bubble: 'news', started_at: '2026-11-18T02:00:01.000Z' }),
      step('seed-news', 'seed', { parent_step_id: 'sub-news', started_at: '2026-11-18T02:00:02.000Z' }),
      step('score-news', 'score', { parent_step_id: 'sub-news', started_at: '2026-11-18T02:00:03.000Z' }),
    ];
    const labels = stepLabels(steps);
    expect(labels.get('seed-news')).toBe('Picked entities for news');
    expect(labels.get('score-news')).toBe('Scored news evidence');
  });

  it('numbers repeats from the second copy, so every row is distinct and early labels never change', () => {
    const steps = [
      step('seed-1', 'seed', { started_at: '2026-11-18T02:00:01.000Z' }),
      step('seed-2', 'seed', { started_at: '2026-11-18T02:00:02.000Z' }),
      step('seed-3', 'seed', { started_at: '2026-11-18T02:00:03.000Z' }),
    ];
    expect([...stepLabels(steps).values()]).toEqual([
      'Picked bubbles',
      'Picked bubbles (2)',
      'Picked bubbles (3)',
    ]);
    expect(stepLabels(steps.slice(0, 1)).get('seed-1')).toBe('Picked bubbles');
  });
});
