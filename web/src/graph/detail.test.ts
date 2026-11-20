import { describe, expect, it } from 'vitest';
import { AGENTIC_STEPS, GAS_CITATION, NORMAL_STEPS } from '../trace/fixtures/stored-runs';
import { globalDetail, nodeMeta, traceDetail } from './detail';
import {
  buildTraceGraph,
  citeNodeId,
  entityNodeId,
  groupNodeId,
  stepNodeId,
  QUESTION_ID,
  type GNode,
} from './model';

const nodeOf = (id: string, nodes: GNode[]) => nodes.find((n) => n.id === id);

describe('traceDetail', () => {
  const graph = buildTraceGraph(NORMAL_STEPS);
  const none = new Set<string>();

  it('shows the internal step name, status, relevance with its number, and source text', () => {
    const d = traceDetail(nodeOf(stepNodeId('n-retrieve'), graph.nodes), NORMAL_STEPS, none);
    expect(d).not.toBeNull();
    expect(d!.kindNote).toBe('Internal step: retrieve');
    expect(d!.title).toBe('Searched Energy');
    expect(d!.status).toBe('ok');
    expect(d!.sourceText).toBe('Gas prices rose 12% in March.');
    expect(d!.rows.find((r) => r.label === 'Items touched')?.value).toBe('4');
  });

  it('shows the relevance band and the number', () => {
    const d = traceDetail(nodeOf(stepNodeId('n-score'), graph.nodes), NORMAL_STEPS, none);
    expect(d!.relevance).toBe(0.5);
    expect(d!.rows.some((r) => r.label === 'Relevance')).toBe(false);
  });

  it('shows the error text for a failed subagent', () => {
    const g = buildTraceGraph(AGENTIC_STEPS);
    const d = traceDetail(nodeOf(stepNodeId('a-sub-policy'), g.nodes), AGENTIC_STEPS, none);
    expect(d!.status).toBe('error');
    expect(d!.error).toBe('Provider timeout after 30s');
  });

  it('a group reports its count and whether it is expanded', () => {
    const closed = traceDetail(nodeOf(groupNodeId('Energy'), graph.nodes), NORMAL_STEPS, none);
    expect(closed!.group).toEqual({ bubble: 'Energy', count: 4, expanded: false });
    const open = traceDetail(nodeOf(groupNodeId('Energy'), graph.nodes), NORMAL_STEPS, new Set(['Energy']));
    expect(open!.group?.expanded).toBe(true);
  });

  it('a cited item lists the source and the steps that cited it', () => {
    const d = traceDetail(nodeOf(citeNodeId(GAS_CITATION.item_id), graph.nodes), NORMAL_STEPS, none);
    expect(d!.kindNote).toBe('Cited item');
    expect(d!.rows.find((r) => r.label === 'Source URL')?.value).toBe(GAS_CITATION.url);
    expect(d!.rows.find((r) => r.label === 'Cited by')?.value).toBe('answer');
  });

  it('the question node has its own description', () => {
    const d = traceDetail(nodeOf(QUESTION_ID, graph.nodes), NORMAL_STEPS, none);
    expect(d!.title).toBe('Your question');
  });

  it('an entity node names its bubble', () => {
    const g = buildTraceGraph(NORMAL_STEPS, { expandedBubbles: new Set(['Energy']) });
    const d = traceDetail(nodeOf(entityNodeId('Energy', 'ent-gas'), g.nodes), NORMAL_STEPS, none);
    expect(d!.rows[0]).toEqual({ label: 'Bubble', value: 'Energy' });
  });

  it('returns null for an unknown node', () => {
    expect(traceDetail(undefined, NORMAL_STEPS, none)).toBeNull();
  });
});

describe('nodeMeta and globalDetail', () => {
  it('describes each node kind in plain words', () => {
    const g = buildTraceGraph(AGENTIC_STEPS);
    expect(nodeMeta(nodeOf(stepNodeId('a-sub-policy'), g.nodes)!)).toBe('Step, Could not finish');
    expect(nodeMeta(nodeOf('bubble:Energy', g.nodes)!)).toBe('Bubble');
  });

  it('global viewer nodes show the bubble and the API kind', () => {
    const d = globalDetail({ id: 'x', label: 'Gas', kind: 'node', bubble: 'Energy', apiKind: 'entity' });
    expect(d!.kindNote).toBe('Node kind: entity');
    expect(d!.rows).toEqual([{ label: 'Bubble', value: 'Energy' }]);
  });
});
