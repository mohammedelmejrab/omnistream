import { orderSteps, relevanceOf, STEP_STATUS_WORD } from '../trace/model';
import type { Citation, Step, StepStatus } from '../trace/types';
import { citeNodeId, type GNode, QUESTION_ID } from './model';

// Detail panel content (spec 10.3). Pure: node in, plain rows out.

export interface DetailRow {
  label: string;
  value: string;
}

export interface DetailModel {
  /** Element id the model belongs to. */
  id: string;
  title: string;
  kindNote: string;
  status: StepStatus | null;
  rows: DetailRow[];
  relevance: number | null;
  sourceText: string | null;
  citations: Citation[];
  error: string | null;
  /** Set on entity groups: the user can expand or collapse them. */
  group: { bubble: string; count: number; expanded: boolean } | null;
}

const MAX_VALUE = 240;

export function formatValue(v: unknown): string {
  let text: string;
  if (v === null || v === undefined) text = 'none';
  else if (typeof v === 'string') text = v;
  else if (typeof v === 'number' || typeof v === 'boolean') text = String(v);
  else if (Array.isArray(v)) text = v.map((x) => formatValue(x)).join(', ');
  else text = JSON.stringify(v);
  return text.length > MAX_VALUE ? `${text.slice(0, MAX_VALUE - 1)}…` : text;
}

function blank(id: string, title: string, kindNote: string): DetailModel {
  return {
    id,
    title,
    kindNote,
    status: null,
    rows: [],
    relevance: null,
    sourceText: null,
    citations: [],
    error: null,
    group: null,
  };
}

function timeText(iso: string): string {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleTimeString();
}

function stepDetail(id: string, step: Step, steps: readonly Step[]): DetailModel {
  const rel = relevanceOf(step, steps);
  const rows: DetailRow[] = [
    { label: 'Bubble', value: step.bubble ?? 'None' },
    { label: 'Started', value: timeText(step.started_at) },
    {
      label: 'Duration',
      value: step.duration_ms === null ? 'Still running' : `${step.duration_ms} ms`,
    },
    { label: 'Items touched', value: String(step.node_ids.length) },
  ];
  // Relevance is shown once, by the panel, as "Relevance: Medium (0.50)".
  for (const [k, v] of Object.entries(step.summary)) {
    if (k === 'source_text' || k === 'relevance') continue;
    rows.push({ label: k.replace(/_/g, ' '), value: formatValue(v) });
  }
  const sourceText =
    typeof step.summary['source_text'] === 'string' ? (step.summary['source_text'] as string) : null;
  return {
    ...blank(id, '', `Internal step: ${step.kind}`),
    status: step.status,
    rows,
    relevance: rel,
    sourceText,
    citations: step.citations,
    error: step.error,
  };
}

/** Detail model for a node in the advanced trace graph. Null when the node is unknown. */
export function traceDetail(
  node: GNode | undefined,
  steps: readonly Step[],
  expanded: ReadonlySet<string>,
): DetailModel | null {
  if (!node) return null;
  const ordered = orderSteps(steps);

  if (node.id === QUESTION_ID) {
    return { ...blank(node.id, 'Your question', 'Start of the run'), title: node.label };
  }

  if (node.kind === 'step' && node.stepId) {
    const step = ordered.find((s) => s.id === node.stepId);
    if (!step) return null;
    return { ...stepDetail(node.id, step, ordered), title: node.label };
  }

  if (node.kind === 'bubble') {
    const touching = ordered.filter((s) => s.bubble === node.bubble);
    const detail = blank(node.id, node.label, 'Bubble');
    detail.rows = [
      { label: 'Steps in this bubble', value: String(touching.length) },
      { label: 'Steps', value: touching.map((s) => s.kind).join(', ') || 'none' },
    ];
    return detail;
  }

  if (node.kind === 'group' && node.bubble) {
    const detail = blank(node.id, node.label, 'Entities and chunks in one bubble');
    detail.group = {
      bubble: node.bubble,
      count: node.count ?? 0,
      expanded: expanded.has(node.bubble),
    };
    detail.rows = [{ label: 'Bubble', value: node.bubble }];
    return detail;
  }

  if (node.kind === 'entity') {
    const detail = blank(node.id, node.label, 'Entity or chunk');
    detail.rows = [{ label: 'Bubble', value: node.bubble ?? 'None' }];
    return detail;
  }

  if (node.kind === 'cite') {
    const citing = ordered.filter((s) => s.citations.some((c) => citeNodeId(c.item_id) === node.id));
    const detail = blank(node.id, node.label, 'Cited item');
    detail.rows = [
      { label: 'Source URL', value: node.url ?? 'No URL' },
      { label: 'Cited by', value: citing.map((s) => s.kind).join(', ') || 'none' },
    ];
    detail.citations = citing.flatMap((s) => s.citations).filter((c) => citeNodeId(c.item_id) === node.id);
    return detail;
  }

  return null;
}

/** Short plain-words description for the parallel list. */
export function nodeMeta(node: GNode): string {
  switch (node.kind) {
    case 'question':
      return 'Start of the run';
    case 'bubble':
      return 'Bubble';
    case 'group':
      return `Collapsed group of ${node.count ?? 0}, select to expand`;
    case 'entity':
      return 'Entity or chunk';
    case 'cite':
      return 'Cited item';
    case 'step':
      return node.status ? `Step, ${STEP_STATUS_WORD[node.status]}` : 'Step';
    default:
      return node.apiKind ?? 'Node';
  }
}

/** Detail model for a node in the global viewer (read-only). */
export function globalDetail(node: GNode | undefined): DetailModel | null {
  if (!node) return null;
  const detail = blank(node.id, node.label, node.apiKind ? `Node kind: ${node.apiKind}` : 'Node');
  detail.rows = [{ label: 'Bubble', value: node.bubble ?? 'None' }];
  return detail;
}
