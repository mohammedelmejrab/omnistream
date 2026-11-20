import { describe, expect, it } from 'vitest';
import { AGENTIC_STEPS, NORMAL_STEPS } from '../trace/fixtures/stored-runs';
import { getCytoscape, GRAPH_STYLE } from './cytoscape';
import { buildTraceGraph, LAYOUT_OPTIONS, stepNodeId, toElements } from './model';

// Runs the real dagre layout headless (no canvas) and checks the two properties the
// spec relies on: live and replay views lay out the same, and the flow reads left to right.

function layout(steps: Parameters<typeof buildTraceGraph>[0]) {
  const cy = getCytoscape()({
    headless: true,
    styleEnabled: true,
    style: GRAPH_STYLE,
    elements: toElements(buildTraceGraph(steps)) as never,
  });
  cy.layout(LAYOUT_OPTIONS as never).run();
  const positions = new Map<string, { x: number; y: number }>();
  cy.nodes().forEach((n) => {
    const p = n.position();
    positions.set(n.id(), { x: Math.round(p.x), y: Math.round(p.y) });
  });
  cy.destroy();
  return positions;
}

describe('trace graph layout (dagre, left to right)', () => {
  it('gives the same positions for the same steps on every run', () => {
    const first = layout(NORMAL_STEPS);
    const second = layout(NORMAL_STEPS);
    expect([...second.entries()]).toEqual([...first.entries()]);
  });

  it('places the question left of the answer', () => {
    const pos = layout(AGENTIC_STEPS);
    const q = pos.get('question');
    const answer = pos.get(stepNodeId('a-answer'));
    expect(q).toBeDefined();
    expect(answer).toBeDefined();
    expect(q!.x).toBeLessThan(answer!.x);
  });
});
