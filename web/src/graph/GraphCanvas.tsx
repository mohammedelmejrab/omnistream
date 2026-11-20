import { forwardRef, useEffect, useImperativeHandle, useRef } from 'react';
import type { Core, ElementDefinition, LayoutOptions, NodeSingular } from 'cytoscape';
import { getCytoscape, GRAPH_STYLE } from './cytoscape';
import { LAYOUT_OPTIONS, type GraphElement } from './model';

// React wrapper around one Cytoscape instance (spec 10.3). The canvas itself is not
// focusable; keyboard users go through the parallel DOM list. Zoom and fit are
// exposed as handles so the buttons work without dragging (WCAG 2.5.7).

export interface GraphCanvasHandle {
  zoomIn(): void;
  zoomOut(): void;
  fit(): void;
  centerOn(id: string): void;
}

export interface GraphCanvasProps {
  elements: GraphElement[];
  /** The node the user is focused on (list or canvas). Gets the active outline and is centred. */
  activeId: string | null;
  /** The node currently running. Pulses for three cycles (never under reduced motion). */
  pulseId: string | null;
  reducedMotion: boolean;
  label: string;
  /**
   * Pixels covered on the right by an overlay (the detail panel below 1280px). The
   * active node is centred in the uncovered area so the overlay never hides it (WCAG 2.4.11).
   */
  overlayInset?: number;
  onNodeActivate(id: string): void;
}

export const PULSE_CYCLES = 3;
export const PULSE_HALF_MS = 300;

export const GraphCanvas = forwardRef<GraphCanvasHandle, GraphCanvasProps>(function GraphCanvas(
  { elements, activeId, pulseId, reducedMotion, label, overlayInset = 0, onNodeActivate },
  ref,
) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const cyRef = useRef<Core | null>(null);
  const hasFitted = useRef(false);
  const activateRef = useRef(onNodeActivate);
  activateRef.current = onNodeActivate;
  // Latest focus and overlay, read by the resize handler (which runs outside React's render).
  const activeIdRef = useRef<string | null>(null);
  const insetRef = useRef(overlayInset);
  insetRef.current = overlayInset;
  // Set once the user zooms or pans. Until then a resize refits the whole graph.
  const userMovedRef = useRef(false);

  // Create the instance once; destroy on unmount.
  useEffect(() => {
    if (!containerRef.current) return;
    const cy = getCytoscape()({
      container: containerRef.current,
      elements: [],
      style: GRAPH_STYLE,
      minZoom: 0.2,
      maxZoom: 3,
      wheelSensitivity: 0.3,
    });
    cy.on('tap', 'node', (evt) => activateRef.current(evt.target.id()));
    for (const ev of ['dragpan', 'scrollzoom', 'pinchzoom']) {
      cy.on(ev, () => {
        userMovedRef.current = true;
      });
    }
    // Zoom level on the element, so tests and assistive tooling can read what the buttons did.
    cy.on('zoom', () => {
      if (containerRef.current) containerRef.current.dataset['zoom'] = cy.zoom().toFixed(3);
    });
    cyRef.current = cy;
    // A side panel that opens or closes changes the canvas size without a window resize.
    // Refit so no part of the graph is clipped by the panel. If the user has zoomed or
    // panned, keep their zoom and only re-centre the focused node.
    const observer =
      typeof ResizeObserver === 'undefined'
        ? null
        : new ResizeObserver(() => {
            cy.resize();
            if (cy.nodes().length === 0) return;
            const id = activeIdRef.current;
            const node = id ? cy.getElementById(id) : null;
            const focused = node !== null && node.nonempty() ? node : null;
            if (!userMovedRef.current) fitView(cy);
            if (focused) keepVisible(cy, focused, insetRef.current);
          });
    if (observer && containerRef.current) observer.observe(containerRef.current);
    return () => {
      observer?.disconnect();
      cy.destroy();
      cyRef.current = null;
      hasFitted.current = false;
    };
  }, []);

  // Rebuild elements when the model changes. Layout is deterministic, so live and replay agree.
  useEffect(() => {
    const cy = cyRef.current;
    if (!cy) return;
    const zoom = cy.zoom();
    const pan = cy.pan();
    // Read the container size now: the first fit must use the final width, not the size at mount.
    cy.resize();
    cy.elements().remove();
    cy.add(elements as unknown as ElementDefinition[]);
    // The layout does not fit on its own; the fit below uses the size read just above.
    cy.layout({ ...LAYOUT_OPTIONS, fit: false } as unknown as LayoutOptions).run();
    if (!hasFitted.current) {
      fitView(cy);
      hasFitted.current = cy.nodes().length > 0;
    } else {
      cy.viewport({ zoom, pan });
    }
  }, [elements]);

  // Active node: class plus centring. With an overlay on the right, centre in the part
  // that is not covered, so the focused node stays visible.
  useEffect(() => {
    const cy = cyRef.current;
    if (!cy) return;
    cy.nodes().removeClass('active');
    activeIdRef.current = activeId;
    if (!activeId) return;
    const node = cy.getElementById(activeId);
    if (node.empty()) return;
    node.addClass('active');
    keepVisible(cy, node, overlayInset);
    // Where the focused node sits inside the canvas, for checks that it is not covered.
    const at = node.renderedPosition();
    if (containerRef.current) {
      containerRef.current.dataset['activeX'] = at.x.toFixed(1);
      containerRef.current.dataset['activeY'] = at.y.toFixed(1);
    }
  }, [activeId, elements, overlayInset]);

  // Running node: pulse for three cycles, then stop. Static under reduced motion.
  useEffect(() => {
    const cy = cyRef.current;
    if (!cy) return;
    cy.nodes().removeClass('pulse');
    if (!pulseId || reducedMotion) return;
    const node = cy.getElementById(pulseId);
    if (node.empty()) return;
    let cycles = 0;
    let on = false;
    const timer = window.setInterval(() => {
      on = !on;
      if (on) {
        node.addClass('pulse');
      } else {
        node.removeClass('pulse');
        cycles += 1;
        if (cycles >= PULSE_CYCLES) window.clearInterval(timer);
      }
    }, PULSE_HALF_MS);
    return () => {
      window.clearInterval(timer);
      node.removeClass('pulse');
    };
  }, [pulseId, reducedMotion, elements]);

  useImperativeHandle(
    ref,
    () => ({
      zoomIn() {
        const cy = cyRef.current;
        if (!cy) return;
        userMovedRef.current = true;
        cy.zoom({ level: Math.min(cy.maxZoom(), cy.zoom() * 1.25), renderedPosition: centre(cy) });
      },
      zoomOut() {
        const cy = cyRef.current;
        if (!cy) return;
        userMovedRef.current = true;
        cy.zoom({ level: Math.max(cy.minZoom(), cy.zoom() / 1.25), renderedPosition: centre(cy) });
      },
      fit() {
        userMovedRef.current = false;
        if (cyRef.current) fitView(cyRef.current);
        const id = activeIdRef.current;
        const node = id ? cyRef.current?.getElementById(id) : null;
        if (cyRef.current && node && node.nonempty() && insetRef.current > 0) {
          recentre(cyRef.current, node, insetRef.current);
        }
      },
      centerOn(id: string) {
        const cy = cyRef.current;
        const node = cy?.getElementById(id);
        if (cy && node && !node.empty()) recentre(cy, node, overlayInset);
      },
    }),
    [overlayInset],
  );

  return (
    <div
      ref={containerRef}
      className="graph-canvas"
      role="img"
      aria-label={label}
      data-testid="graph-canvas"
    />
  );
});

/** Largest zoom a fit may produce. A small graph would otherwise blow its nodes up to fill the canvas. */
export const FIT_MAX_ZOOM = 1.3;

/** Fit the whole graph with padding, capped at FIT_MAX_ZOOM and centred. */
function fitView(cy: Core): void {
  cy.fit(undefined, LAYOUT_OPTIONS.padding);
  if (cy.zoom() > FIT_MAX_ZOOM) {
    cy.zoom(FIT_MAX_ZOOM);
    cy.center();
  }
}

function centre(cy: Core): { x: number; y: number } {
  return { x: cy.width() / 2, y: cy.height() / 2 };
}

/**
 * Make sure a focused node is visible: leave the view alone if the node is already in the
 * uncovered part of the canvas, otherwise centre it there. Centring unconditionally would
 * pan a fitted graph onto whichever node was focused first.
 */
function keepVisible(cy: Core, node: NodeSingular, overlayInset: number): void {
  const at = node.renderedPosition();
  const margin = 24;
  const right = cy.width() - overlayInset;
  const inside =
    at.x >= margin && at.x <= right - margin && at.y >= margin && at.y <= cy.height() - margin;
  if (!inside) recentre(cy, node, overlayInset);
}

/** Centre a node in the uncovered part of the canvas (see overlayInset). */
function recentre(cy: Core, node: NodeSingular, overlayInset: number): void {
  cy.center(node);
  if (overlayInset > 0) cy.panBy({ x: -overlayInset / 2, y: 0 });
}
