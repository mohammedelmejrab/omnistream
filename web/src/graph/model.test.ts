import { describe, expect, it } from 'vitest';
import { AGENTIC_STEPS, GAS_CITATION, NORMAL_STEPS } from '../trace/fixtures/stored-runs';
import type { GraphResponse } from '../api/types';
import {
  answerPath,
  buildGlobalGraph,
  buildTraceGraph,
  citeNodeId,
  entityNodeId,
  groupNodeId,
  LAYOUT_OPTIONS,
  QUESTION_ID,
  stepNodeId,
  toElements,
} from './model';

const endpointsExist = (g: { nodes: { id: string }[]; edges: { source: string; target: string }[] }) => {
  const ids = new Set(g.nodes.map((n) => n.id));
  return g.edges.every((e) => ids.has(e.source) && ids.has(e.target));
};

describe('buildTraceGraph', () => {
  it('starts from the question and has one node per step, with friendly labels', () => {
    const g = buildTraceGraph(NORMAL_STEPS);
    expect(g.nodes.find((n) => n.id === QUESTION_ID)?.label).toBe('Your question');
    expect(g.nodes.find((n) => n.id === stepNodeId('n-retrieve'))?.label).toBe('Searched Energy');
    expect(g.nodes.find((n) => n.id === stepNodeId('n-answer'))?.label).toBe('Answer');
  });

  it('every edge points at nodes that exist (no dangling edges)', () => {
    expect(endpointsExist(buildTraceGraph(NORMAL_STEPS))).toBe(true);
    expect(endpointsExist(buildTraceGraph(AGENTIC_STEPS))).toBe(true);
    expect(endpointsExist(buildTraceGraph(AGENTIC_STEPS.slice(0, 3)))).toBe(true);
  });

  it('a step whose parent is not revealed yet hangs from the question', () => {
    const g = buildTraceGraph(NORMAL_STEPS.slice(3)); // score and answer, no route/seed/retrieve
    expect(g.edges.some((e) => e.source === QUESTION_ID && e.target === stepNodeId('n-score'))).toBe(true);
    expect(endpointsExist(g)).toBe(true);
  });

  it('collapses entities and chunks into one count per bubble', () => {
    const g = buildTraceGraph(NORMAL_STEPS);
    const group = g.nodes.find((n) => n.id === groupNodeId('Energy'));
    expect(group).toMatchObject({ kind: 'group', count: 4, label: 'Energy: 4 entities and chunks' });
    expect(g.nodes.some((n) => n.kind === 'entity')).toBe(false);
  });

  it('expands a bubble group into child nodes when asked', () => {
    const g = buildTraceGraph(NORMAL_STEPS, { expandedBubbles: new Set(['Energy']) });
    const children = g.nodes.filter((n) => n.parent === groupNodeId('Energy'));
    expect(children.map((n) => n.id)).toEqual([
      entityNodeId('Energy', 'ent-gas'),
      entityNodeId('Energy', 'ent-march'),
      entityNodeId('Energy', 'chunk-7'),
      entityNodeId('Energy', 'chunk-9'),
    ]);
    expect(endpointsExist(g)).toBe(true);
  });

  it('adds one node per cited item and links it to the answer', () => {
    const g = buildTraceGraph(NORMAL_STEPS);
    expect(g.nodes.find((n) => n.id === citeNodeId(GAS_CITATION.item_id))).toMatchObject({
      kind: 'cite',
      label: GAS_CITATION.title,
      url: GAS_CITATION.url,
    });
    expect(
      g.edges.some((e) => e.source === citeNodeId(GAS_CITATION.item_id) && e.target === stepNodeId('n-answer')),
    ).toBe(true);
  });

  it('is deterministic: the same steps give the same graph', () => {
    expect(buildTraceGraph(AGENTIC_STEPS)).toEqual(buildTraceGraph([...AGENTIC_STEPS].reverse()));
  });
});

describe('answerPath', () => {
  it('runs from the answer back through the cited item and the steps that found it', () => {
    const path = answerPath(NORMAL_STEPS);
    expect(path.has(stepNodeId('n-answer'))).toBe(true);
    expect(path.has(citeNodeId(GAS_CITATION.item_id))).toBe(true);
    expect(path.has(stepNodeId('n-retrieve'))).toBe(false); // the retrieve step did not cite it
    expect(path.has(stepNodeId('n-route'))).toBe(false);
  });

  it('includes the ancestors of a step that produced a cited item', () => {
    const steps = AGENTIC_STEPS.map((s) =>
      s.id === 'a-sub-energy' ? { ...s, citations: [GAS_CITATION] } : s,
    );
    const path = answerPath(steps);
    expect(path.has(stepNodeId('a-sub-energy'))).toBe(true);
    expect(path.has(stepNodeId('a-seed'))).toBe(true);
    expect(path.has(stepNodeId('a-route'))).toBe(true);
    expect(path.has('bubble:Energy')).toBe(true);
    expect(path.has(stepNodeId('a-sub-policy'))).toBe(false);
  });

  it('is empty before the answer exists', () => {
    expect(answerPath(NORMAL_STEPS.slice(0, 4)).size).toBe(0);
  });
});

describe('toElements', () => {
  it('without a focus, nothing is dimmed', () => {
    const els = toElements(buildTraceGraph(NORMAL_STEPS));
    expect(els.some((e) => e.classes.includes('dimmed'))).toBe(false);
  });

  it('with a focus, everything off the path is dimmed and the path is kept', () => {
    const focus = answerPath(NORMAL_STEPS);
    const els = toElements(buildTraceGraph(NORMAL_STEPS), { focus });
    const dimmedNodes = els.filter((e) => e.group === 'nodes' && e.classes.includes('dimmed'));
    const pathNodes = els.filter((e) => e.group === 'nodes' && e.classes.includes('path'));
    expect(dimmedNodes.length).toBeGreaterThan(0);
    expect(pathNodes.map((e) => e.data.id).sort()).toEqual([...focus].sort());
  });

  it('carries kind and status as classes, and the parent for compound nodes', () => {
    const els = toElements(buildTraceGraph(AGENTIC_STEPS, { expandedBubbles: new Set(['Energy']) }));
    const failed = els.find((e) => e.data.id === stepNodeId('a-sub-policy'));
    expect(failed?.classes).toContain('status-error');
    expect(failed?.classes).toContain('kind-step');
    const child = els.find((e) => e.data.id === entityNodeId('Energy', 'ent-gas'));
    expect(child?.data.parent).toBe(groupNodeId('Energy'));
  });
});

describe('buildGlobalGraph', () => {
  const resp: GraphResponse = {
    nodes: [
      { id: 'a', label: 'Gas', bubble: 'Energy', kind: 'entity' },
      { id: 'b', label: 'Oil', bubble: 'Energy', kind: 'entity' },
      { id: 'c', label: 'Vote', bubble: 'Policy', kind: 'chunk' },
    ],
    edges: [
      { id: 'e1', source: 'a', target: 'b', label: 'related' },
      { id: 'e2', source: 'a', target: 'missing', label: 'broken' },
    ],
    total: 3,
  };

  it('keeps nodes and edges and drops edges whose ends are not loaded', () => {
    const g = buildGlobalGraph(resp);
    expect(g.nodes).toHaveLength(3);
    expect(g.edges.map((e) => e.id)).toEqual(['e1']);
    expect(endpointsExist(g)).toBe(true);
  });

  it('keeps the API node kind for the kind filter and the list', () => {
    const g = buildGlobalGraph(resp);
    expect(g.nodes.find((n) => n.id === 'c')?.apiKind).toBe('chunk');
  });
});

describe('layout options', () => {
  it('uses a left-to-right layered layout (dagre) with no animation', () => {
    expect(LAYOUT_OPTIONS).toMatchObject({ name: 'dagre', rankDir: 'LR', animate: false });
  });
});
