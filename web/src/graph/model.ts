import { bubblesOf, orderSteps, stepLabels } from '../trace/model';
import type { Citation, GraphResponse, Step, StepKind, StepStatus } from '../trace/types';

// Graph model for the Advanced trace (spec 10.3) and the global viewer (spec 10.5).
// Pure data in, plain nodes and edges out. Cytoscape elements are derived from this
// in toElements(), so the rules here can be tested without a canvas.

export const QUESTION_ID = 'question';

/** Nodes per page in the global viewer (spec 10.5, decision 32). */
export const GRAPH_PAGE_SIZE = 300;

export type NodeKind = 'question' | 'bubble' | 'step' | 'group' | 'entity' | 'cite' | 'node';

export interface GNode {
  id: string;
  label: string;
  kind: NodeKind;
  bubble: string | null;
  /** Compound parent (entities inside their bubble's group). */
  parent?: string;
  stepId?: string;
  stepKind?: StepKind;
  status?: StepStatus;
  url?: string | null;
  /** Number of entities or chunks a group stands for. */
  count?: number;
  /** For the global viewer: the node kind from the API (entity, chunk, ...). */
  apiKind?: string;
}

export interface GEdge {
  id: string;
  source: string;
  target: string;
}

export interface GraphModel {
  nodes: GNode[];
  edges: GEdge[];
}

/** Cytoscape-compatible element, kept free of the cytoscape import. */
export interface GraphElement {
  group: 'nodes' | 'edges';
  data: Record<string, unknown>;
  classes: string;
}

export const stepNodeId = (stepId: string) => `step:${stepId}`;
export const bubbleNodeId = (bubble: string) => `bubble:${bubble}`;
export const groupNodeId = (bubble: string) => `group:${bubble}`;
export const entityNodeId = (bubble: string, entity: string) => `ent:${bubble}:${entity}`;
export const citeNodeId = (itemId: string) => `cite:${itemId}`;

const EVIDENCE_KINDS: StepKind[] = ['retrieve', 'subagent', 'score'];

export interface TraceGraphOptions {
  /** Bubbles whose entity/chunk group is expanded into single nodes. */
  expandedBubbles?: ReadonlySet<string>;
}

/**
 * Advanced trace graph for one run's steps (the whole run, or the revealed prefix during replay).
 * Structure: question -> bubble -> step tree; evidence steps -> entity group per bubble;
 * cited items -> answer.
 */
export function buildTraceGraph(stepsIn: readonly Step[], opts: TraceGraphOptions = {}): GraphModel {
  const steps = orderSteps(stepsIn);
  const stepIds = new Set(steps.map((s) => s.id));
  const bubbles = bubblesOf(steps);
  const labels = stepLabels(steps);
  const nodes: GNode[] = [{ id: QUESTION_ID, label: 'Your question', kind: 'question', bubble: null }];
  const edges: GEdge[] = [];
  const edgeIds = new Set<string>();
  const addEdge = (source: string, target: string) => {
    const id = `${source}->${target}`;
    if (edgeIds.has(id)) return;
    edgeIds.add(id);
    edges.push({ id, source, target });
  };

  for (const b of bubbles) {
    nodes.push({ id: bubbleNodeId(b), label: b, kind: 'bubble', bubble: b });
    addEdge(QUESTION_ID, bubbleNodeId(b));
  }

  for (const s of steps) {
    nodes.push({
      id: stepNodeId(s.id),
      label: labels.get(s.id) ?? s.kind,
      kind: 'step',
      bubble: s.bubble,
      stepId: s.id,
      stepKind: s.kind,
      status: s.status,
    });
  }

  for (const s of steps) {
    const parent =
      s.parent_step_id && stepIds.has(s.parent_step_id) ? stepNodeId(s.parent_step_id) : QUESTION_ID;
    addEdge(parent, stepNodeId(s.id));
    if (s.bubble && bubbles.includes(s.bubble) && EVIDENCE_KINDS.includes(s.kind)) {
      addEdge(bubbleNodeId(s.bubble), stepNodeId(s.id));
    }
  }

  for (const b of bubbles) {
    const entities = uniq(
      steps.filter((s) => s.bubble === b && EVIDENCE_KINDS.includes(s.kind)).flatMap((s) => s.node_ids),
    );
    if (entities.length === 0) continue;
    const gid = groupNodeId(b);
    nodes.push({
      id: gid,
      label: `${b}: ${entities.length} entities and chunks`,
      kind: 'group',
      bubble: b,
      count: entities.length,
    });
    addEdge(bubbleNodeId(b), gid);
    if (opts.expandedBubbles?.has(b)) {
      for (const e of entities) {
        nodes.push({ id: entityNodeId(b, e), label: e, kind: 'entity', bubble: b, parent: gid });
      }
    }
  }

  const citations = new Map<string, Citation>();
  for (const s of steps) for (const c of s.citations) if (!citations.has(c.item_id)) citations.set(c.item_id, c);
  for (const c of citations.values()) {
    nodes.push({ id: citeNodeId(c.item_id), label: c.title || c.item_id, kind: 'cite', bubble: null, url: c.url });
  }
  for (const s of steps) {
    for (const c of s.citations) {
      if (s.kind === 'answer') addEdge(citeNodeId(c.item_id), stepNodeId(s.id));
      else addEdge(stepNodeId(s.id), citeNodeId(c.item_id));
    }
  }

  return { nodes, edges };
}

function uniq<T>(xs: readonly T[]): T[] {
  return [...new Set(xs)];
}

/**
 * Nodes on the path from the final answer back to the cited sources (spec 10.3):
 * the answer, each cited item, the steps that produced them, their ancestors and bubbles.
 */
export function answerPath(stepsIn: readonly Step[]): Set<string> {
  const steps = orderSteps(stepsIn);
  const byId = new Map(steps.map((s) => [s.id, s] as const));
  const answers = steps.filter((s) => s.kind === 'answer');
  const answer = answers[answers.length - 1];
  const out = new Set<string>();
  if (!answer) return out;
  out.add(stepNodeId(answer.id));

  const addWithAncestors = (start: Step) => {
    const seen = new Set<string>();
    let cur: Step | undefined = start;
    while (cur && !seen.has(cur.id)) {
      seen.add(cur.id);
      out.add(stepNodeId(cur.id));
      if (cur.bubble) out.add(bubbleNodeId(cur.bubble));
      cur = cur.parent_step_id ? byId.get(cur.parent_step_id) : undefined;
    }
  };

  for (const c of answer.citations) {
    out.add(citeNodeId(c.item_id));
    for (const s of steps) {
      if (s.kind !== 'answer' && s.citations.some((x) => x.item_id === c.item_id)) addWithAncestors(s);
    }
  }
  return out;
}

/** Global viewer model from the API response (spec 12, GET /api/graph). */
export function buildGlobalGraph(resp: GraphResponse): GraphModel {
  const nodes: GNode[] = resp.nodes.map((n) => ({
    id: n.id,
    label: n.label,
    kind: 'node',
    bubble: n.bubble,
    apiKind: n.kind,
  }));
  const ids = new Set(nodes.map((n) => n.id));
  const edges: GEdge[] = resp.edges
    .filter((e) => ids.has(e.source) && ids.has(e.target))
    .map((e) => ({ id: e.id, source: e.source, target: e.target }));
  return { nodes, edges };
}

export interface ViewState {
  /** When set, only these node ids (and edges between them) are emphasised; the rest dim. */
  focus?: ReadonlySet<string> | null;
}

/** Cytoscape-ready elements. Dimmed items keep a visible outline (see graph/style.ts). */
export function toElements(model: GraphModel, view: ViewState = {}): GraphElement[] {
  const focus = view.focus ?? null;
  const out: GraphElement[] = [];
  for (const n of model.nodes) {
    const data: Record<string, unknown> = {
      id: n.id,
      label: n.label,
      kind: n.kind,
      bubble: n.bubble,
    };
    if (n.parent) data.parent = n.parent;
    if (n.stepId) data.stepId = n.stepId;
    if (n.stepKind) data.stepKind = n.stepKind;
    if (n.status) data.status = n.status;
    if (n.url !== undefined) data.url = n.url;
    if (n.count !== undefined) data.count = n.count;
    if (n.apiKind) data.apiKind = n.apiKind;
    const classes = [`kind-${n.kind}`];
    if (n.status) classes.push(`status-${n.status}`);
    if (focus) classes.push(focus.has(n.id) ? 'path' : 'dimmed');
    out.push({ group: 'nodes', data, classes: classes.join(' ') });
  }
  for (const e of model.edges) {
    const onPath = focus ? focus.has(e.source) && focus.has(e.target) : false;
    const classes = focus ? (onPath ? 'path' : 'dimmed') : '';
    out.push({ group: 'edges', data: { id: e.id, source: e.source, target: e.target }, classes });
  }
  return out;
}

export const LAYOUT_OPTIONS = {
  name: 'dagre',
  rankDir: 'LR',
  nodeSep: 16,
  rankSep: 36,
  edgeSep: 12,
  padding: 28,
  animate: false,
  fit: true,
} as const;
