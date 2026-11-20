import type { Citation, Run, RunStatus, Step, StepKind, StepStatus } from './types';

// Pure helpers shared by the simple view, the advanced graph and replay.
// No React here so every rule can be unit tested directly.

export const KIND_ORDER: StepKind[] = [
  'route',
  'seed',
  'retrieve',
  'score',
  'subagent',
  'join',
  'merge',
  'answer',
];

/** Internal step names, shown only in the detail panel (spec 10.3). */
export const STEP_STATUS_WORD: Record<StepStatus, string> = {
  running: 'Working',
  ok: 'Done',
  error: 'Could not finish',
  cancelled: 'Stopped',
};

export const RUN_STATUS_WORD: Record<RunStatus, string> = {
  running: 'Running',
  ok: 'Done',
  failed: 'Failed',
  cancelled: 'Stopped',
  interrupted: 'Interrupted',
};

/** Friendly graph label for a step (spec 10.3: the graph uses friendly labels). */
export function friendlyStepLabel(step: Pick<Step, 'kind' | 'bubble'>): string {
  const b = step.bubble;
  switch (step.kind) {
    case 'route':
      return 'Understood question';
    case 'seed':
      return 'Picked bubbles';
    case 'retrieve':
      return b ? `Searched ${b}` : 'Searched bubbles';
    case 'score':
      return b ? `Scored ${b} evidence` : 'Scored evidence';
    case 'subagent':
      return b ? `${b} subagent` : 'Subagent';
    case 'join':
      return 'Joined entities';
    case 'merge':
      return 'Merged answer';
    case 'answer':
      return 'Answer';
  }
}

/**
 * Bubble a step belongs to: its own, else the nearest ancestor's. The backend leaves
 * `bubble` null on seed and score steps, so the bubble comes from the step tree.
 */
function bubbleOf(step: Step, byId: ReadonlyMap<string, Step>): string | null {
  const seen = new Set<string>();
  let cur: Step | undefined = step;
  while (cur && !seen.has(cur.id)) {
    if (cur.bubble) return cur.bubble;
    seen.add(cur.id);
    cur = cur.parent_step_id ? byId.get(cur.parent_step_id) : undefined;
  }
  return null;
}

/**
 * Label for each step in the run. Seed and score steps name their bubble. When a label
 * still repeats (two steps for the same bubble), the second and later copies get a number,
 * so every row in the step list is distinct. Numbering starts at the second copy, so a
 * label never changes when the replay reveals more steps.
 */
export function stepLabels(steps: readonly Step[]): Map<string, string> {
  const ordered = orderSteps(steps);
  const byId = new Map(ordered.map((s) => [s.id, s] as const));
  const out = new Map<string, string>();
  const seenCount = new Map<string, number>();
  for (const s of ordered) {
    const bubble = s.kind === 'seed' || s.kind === 'score' ? bubbleOf(s, byId) : s.bubble;
    let label = friendlyStepLabel({ kind: s.kind, bubble });
    if (s.kind === 'seed' && bubble) label = `Picked entities for ${bubble}`;
    const n = (seenCount.get(label) ?? 0) + 1;
    seenCount.set(label, n);
    out.set(s.id, n > 1 ? `${label} (${n})` : label);
  }
  return out;
}

function kindRank(kind: StepKind): number {
  return KIND_ORDER.indexOf(kind);
}

function startedMs(step: Step): number {
  const t = Date.parse(step.started_at);
  return Number.isNaN(t) ? 0 : t;
}

/** Stable order: start time, then pipeline stage, then id. */
export function orderSteps(steps: readonly Step[]): Step[] {
  return [...steps].sort((a, b) => {
    const dt = startedMs(a) - startedMs(b);
    if (dt !== 0) return dt;
    const dk = kindRank(a.kind) - kindRank(b.kind);
    if (dk !== 0) return dk;
    return a.id < b.id ? -1 : a.id > b.id ? 1 : 0;
  });
}

/**
 * Upsert one step by id (live events arrive on start and on finish).
 * Status only moves forward: a late "running" copy never overwrites a finished step,
 * which can happen when a catch-up fetch races the event stream.
 */
export function mergeStep(steps: readonly Step[], incoming: Step): Step[] {
  const idx = steps.findIndex((s) => s.id === incoming.id);
  if (idx === -1) return orderSteps([...steps, incoming]);
  const existing = steps[idx];
  if (existing && existing.status !== 'running' && incoming.status === 'running') return steps.slice();
  const next = steps.slice();
  next[idx] = incoming;
  return orderSteps(next);
}

export function mergeSteps(steps: readonly Step[], incoming: readonly Step[]): Step[] {
  let out = orderSteps(steps);
  for (const s of incoming) out = mergeStep(out, s);
  return out;
}

export type RelevanceBand = 'Low' | 'Medium' | 'High';

/** Low / Medium / High; the number is shown on hover and in the detail text. */
export function relevanceBand(value: number): RelevanceBand {
  if (value >= 0.66) return 'High';
  if (value >= 0.33) return 'Medium';
  return 'Low';
}

function clamp01(n: number): number {
  return Math.min(1, Math.max(0, n));
}

function finiteNumber(v: unknown): number | null {
  return typeof v === 'number' && Number.isFinite(v) ? v : null;
}

/** Reads a 0..1 relevance from a step summary's `relevance` key, or null when absent. */
export function stepRelevance(step: Pick<Step, 'summary'>): number | null {
  const v = finiteNumber(step.summary['relevance']);
  return v === null ? null : clamp01(v);
}

/**
 * Best score in a retrieve step's `top_facts` (the backend's shape: each entry has a
 * `score`). Null when the step has none.
 */
function topFactScore(step: Pick<Step, 'summary'>): number | null {
  const top = step.summary['top_facts'];
  if (!Array.isArray(top)) return null;
  const scores = top
    .map((f) => (f && typeof f === 'object' ? finiteNumber((f as { score?: unknown }).score) : null))
    .filter((x): x is number => x !== null);
  return scores.length ? clamp01(Math.max(...scores)) : null;
}

/**
 * Relevance of a step, 0..1, or null. A step's own `relevance` wins; otherwise the best
 * retrieve score of the step itself. A subagent has no score of its own, so it takes the
 * best score among the steps under it in the step tree (its searches, seeds and scores).
 */
export function relevanceOf(step: Step, steps: readonly Step[]): number | null {
  const own = stepRelevance(step) ?? topFactScore(step);
  if (own !== null) return own;
  if (step.kind !== 'subagent') return null;
  // Best score anywhere under the subagent (its searches, and the seeds and scores under them).
  const scores: number[] = [];
  const seen = new Set<string>([step.id]);
  let frontier = [step.id];
  while (frontier.length > 0) {
    const next: string[] = [];
    for (const child of steps) {
      if (child.parent_step_id === null || !frontier.includes(child.parent_step_id)) continue;
      if (seen.has(child.id)) continue;
      seen.add(child.id);
      next.push(child.id);
      const v = stepRelevance(child) ?? topFactScore(child);
      if (v !== null) scores.push(v);
    }
    frontier = next;
  }
  return scores.length ? Math.max(...scores) : null;
}

/**
 * Items a step found. Reads `count` when a step carries it; otherwise facts plus chunks
 * (the backend's retrieve and subagent summaries); otherwise the node ids it touched.
 */
export function stepCount(step: Pick<Step, 'summary' | 'node_ids'>): number {
  const c = finiteNumber(step.summary['count']);
  if (c !== null) return c;
  const facts = finiteNumber(step.summary['facts']);
  const chunks = finiteNumber(step.summary['chunks']);
  if (facts !== null || chunks !== null) return (facts ?? 0) + (chunks ?? 0);
  return step.node_ids.length;
}

/** Distinct bubbles in first-seen order: route picks first, then per-step bubbles. */
export function bubblesOf(steps: readonly Step[]): string[] {
  const seen: string[] = [];
  const add = (b: string | null | undefined) => {
    if (b && !seen.includes(b)) seen.push(b);
  };
  for (const s of steps) {
    if (s.kind === 'route') {
      const picked = s.summary['bubbles'];
      if (Array.isArray(picked)) picked.forEach((x) => typeof x === 'string' && add(x));
    }
  }
  for (const s of orderSteps(steps)) {
    if (s.kind === 'seed' || s.kind === 'subagent' || s.kind === 'retrieve') add(s.bubble);
  }
  return seen;
}

export type StageKey = 'understood' | 'searched' | 'gathered' | 'wrote';
export type StageStatus = 'done' | 'working' | 'failed' | 'no-evidence' | 'pending';

export const STAGE_STATUS_WORD: Record<StageStatus, string> = {
  done: 'Done',
  working: 'Working',
  failed: 'Could not finish',
  'no-evidence': 'No evidence',
  pending: 'Waiting',
};

export interface EvidenceItem {
  key: string;
  label: string;
  status: StepStatus;
  relevance: number | null;
  count: number;
  error: string | null;
  stepId: string;
}

export interface Stage {
  key: StageKey;
  title: string;
  status: StageStatus;
  /** Index in the ordered step list of the first step of this stage, or -1. */
  firstIndex: number;
  durationMs: number | null;
  stepIds: string[];
  bubbles: string[];
  items: EvidenceItem[];
  citations: Citation[];
  error: string | null;
  noEvidence: boolean;
}

export interface SimpleView {
  stages: Stage[];
  highlightAnswer: boolean;
}

const STAGE_TITLES: Record<StageKey, string> = {
  understood: 'Understood your question',
  searched: 'Searched bubbles',
  gathered: 'Gathered evidence',
  wrote: 'Wrote answer',
};

function sumDuration(steps: readonly Step[]): number | null {
  const known = steps.filter((s) => s.duration_ms !== null);
  if (known.length === 0) return null;
  return known.reduce((acc, s) => acc + (s.duration_ms ?? 0), 0);
}

function aggregateStatus(
  steps: readonly Step[],
  opts: { complete: boolean },
): StageStatus {
  if (steps.length === 0) {
    // Nothing recorded for this stage: still waiting while the run is live,
    // otherwise the stage never happened.
    return opts.complete ? 'failed' : 'pending';
  }
  if (steps.some((s) => s.status === 'running')) return 'working';
  if (steps.some((s) => s.status === 'error')) return 'failed';
  if (steps.some((s) => s.status === 'cancelled')) return 'failed';
  return 'done';
}

/**
 * Four-stage view (spec 10.2). Pass the steps revealed so far during replay,
 * and `complete` only when the run has finished and every step is shown.
 */
export function buildSimpleView(
  _run: Pick<Run, 'mode' | 'status'>,
  allSteps: readonly Step[],
  opts: { complete: boolean },
): SimpleView {
  const steps = orderSteps(allSteps);
  const indexOf = (s: Step) => steps.indexOf(s);
  const byKind = (...kinds: StepKind[]) => steps.filter((s) => kinds.includes(s.kind));
  const { complete } = opts;

  // Stage 1: understood the question (route).
  const routeSteps = byKind('route');
  const understood: Stage = {
    key: 'understood',
    title: STAGE_TITLES.understood,
    status: aggregateStatus(routeSteps, { complete }),
    firstIndex: routeSteps[0] ? indexOf(routeSteps[0]) : -1,
    durationMs: sumDuration(routeSteps),
    stepIds: routeSteps.map((s) => s.id),
    bubbles: [],
    items: [],
    citations: [],
    error: routeSteps.find((s) => s.error)?.error ?? null,
    noEvidence: false,
  };

  // Stage 2: searched bubbles. The backend records no seed step, so the stage
  // follows the first searches (retrieve, or a subagent in Agentic) when there is no seed.
  const seedSteps = byKind('seed');
  const searchSteps = seedSteps.length > 0 ? seedSteps : byKind('retrieve', 'subagent');
  const searched: Stage = {
    key: 'searched',
    title: STAGE_TITLES.searched,
    status: aggregateStatus(searchSteps, { complete }),
    firstIndex: searchSteps[0] ? indexOf(searchSteps[0]) : -1,
    durationMs: sumDuration(searchSteps),
    stepIds: searchSteps.map((s) => s.id),
    bubbles: bubblesOf(steps),
    items: [],
    citations: [],
    error: searchSteps.find((s) => s.error)?.error ?? null,
    noEvidence: false,
  };

  // Stage 3: gathered evidence. Agentic: one item per bubble subagent.
  // Normal: a single total from the retrieve steps.
  const gatherSteps = byKind('retrieve', 'score', 'subagent', 'join', 'merge');
  const subagents = byKind('subagent');
  let items: EvidenceItem[];
  if (subagents.length > 0) {
    items = subagents.map((s) => ({
      key: s.id,
      label: s.bubble ?? 'Bubble',
      status: s.status,
      relevance: relevanceOf(s, steps),
      count: stepCount(s),
      error: s.error,
      stepId: s.id,
    }));
  } else {
    const retrieves = byKind('retrieve');
    const total = retrieves.reduce((acc, s) => acc + stepCount(s), 0);
    const worst = retrieves.find((s) => s.status === 'error') ?? null;
    const scores = [...byKind('score'), ...retrieves]
      .map((s) => relevanceOf(s, steps))
      .filter((x): x is number => x !== null);
    const relevance = scores.length ? Math.max(...scores) : null;
    items =
      retrieves.length === 0
        ? []
        : [
            {
              key: 'total',
              label: 'All selected bubbles',
              status: worst ? 'error' : retrieves.some((s) => s.status === 'running') ? 'running' : 'ok',
              relevance,
              count: total,
              error: worst?.error ?? null,
              stepId: retrieves[0]?.id ?? '',
            },
          ];
  }
  const failedAll = items.length > 0 && items.every((i) => i.status === 'error');
  const noEvidence = items.length > 0 && items.every((i) => i.count === 0 && i.status !== 'error');
  let gatheredStatus: StageStatus;
  if (gatherSteps.length === 0) {
    gatheredStatus = complete ? 'failed' : 'pending';
  } else if (gatherSteps.some((s) => s.status === 'running')) {
    gatheredStatus = 'working';
  } else if (failedAll) {
    gatheredStatus = 'failed';
  } else if (noEvidence) {
    gatheredStatus = 'no-evidence';
  } else {
    gatheredStatus = 'done';
  }
  const gathered: Stage = {
    key: 'gathered',
    title: STAGE_TITLES.gathered,
    status: gatheredStatus,
    firstIndex: gatherSteps[0] ? indexOf(gatherSteps[0]) : -1,
    durationMs: sumDuration(gatherSteps),
    stepIds: gatherSteps.map((s) => s.id),
    bubbles: [],
    items,
    citations: [],
    error: gatherSteps.find((s) => s.error)?.error ?? null,
    noEvidence: gatheredStatus === 'no-evidence',
  };
  // Stage 4: wrote the answer (answer step, citations as numbered chips).
  const answerSteps = byKind('answer');
  const answerStep = answerSteps[answerSteps.length - 1];
  const wroteStatus: StageStatus = answerStep
    ? aggregateStatus([answerStep], { complete })
    : complete
      ? 'failed'
      : 'pending';
  const wrote: Stage = {
    key: 'wrote',
    title: STAGE_TITLES.wrote,
    status: wroteStatus,
    firstIndex: answerStep ? indexOf(answerStep) : -1,
    durationMs: sumDuration(answerSteps),
    stepIds: answerSteps.map((s) => s.id),
    bubbles: [],
    items: [],
    citations: answerStep ? answerStep.citations : [],
    error: answerStep?.error ?? null,
    noEvidence: false,
  };

  return {
    stages: [understood, searched, gathered, wrote],
    highlightAnswer: Boolean(answerStep),
  };
}

/** Index of the stage replay is currently on (-1 when nothing revealed). */
export function currentStageIndex(view: SimpleView, cursor: number): number {
  let current = -1;
  view.stages.forEach((stage, i) => {
    if (stage.firstIndex !== -1 && stage.firstIndex < cursor) current = i;
  });
  return current;
}

export function citationNumber(citations: readonly Citation[], itemId: string): number {
  return citations.findIndex((c) => c.item_id === itemId) + 1;
}

export function failureText(run: Pick<Run, 'status' | 'error'>): string | null {
  switch (run.status) {
    case 'failed':
      return run.error ?? 'The run failed.';
    case 'cancelled':
      return 'Stopped';
    case 'interrupted':
      return 'Interrupted when OmniStream restarted';
    default:
      return null;
  }
}

