// Test double for GraphCanvas. jsdom has no canvas, so component tests swap the real
// Cytoscape wrapper for this stub (vi.mock). It records zoom and fit calls and exposes
// the element count and focus state as data attributes.
import { createElement, forwardRef, useImperativeHandle } from 'react';
import type { GraphCanvasHandle, GraphCanvasProps } from '../GraphCanvas';

export const canvasSpies = {
  zoomIn: () => undefined as void,
  zoomOut: () => undefined as void,
  fit: () => undefined as void,
  centerOn: (_id: string) => undefined as void,
};

export const GraphCanvas = forwardRef<GraphCanvasHandle, GraphCanvasProps>(function GraphCanvasStub(
  props,
  ref,
) {
  useImperativeHandle(
    ref,
    () => ({
      zoomIn: () => canvasSpies.zoomIn(),
      zoomOut: () => canvasSpies.zoomOut(),
      fit: () => canvasSpies.fit(),
      centerOn: (id: string) => canvasSpies.centerOn(id),
    }),
    [],
  );
  const nodes = props.elements.filter((e) => e.group === 'nodes');
  const dimmed = nodes.filter((e) => e.classes.includes('dimmed')).length;
  return createElement('div', {
    'data-testid': 'graph-canvas',
    'data-count': String(nodes.length),
    'data-dimmed': String(dimmed),
    'data-active': props.activeId ?? '',
    'data-pulse': props.pulseId ?? '',
    role: 'img',
    'aria-label': props.label,
  });
});
