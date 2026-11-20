import cytoscape, { type StylesheetStyle } from 'cytoscape';
import dagre from 'cytoscape-dagre';

// Catppuccin Mocha values (spec section 11). Kept here because Cytoscape styles
// take literal colours, not CSS variables.
export const MOCHA = {
  base: '#1e1e2e',
  mantle: '#181825',
  surface0: '#313244',
  surface1: '#45475a',
  surface2: '#585b70',
  overlay0: '#6c7086',
  overlay1: '#7f849c',
  overlay2: '#9399b2',
  subtext0: '#a6adc8',
  text: '#cdd6f4',
  lavender: '#b4befe',
  teal: '#94e2d5',
  sky: '#89dceb',
  green: '#a6e3a1',
  peach: '#fab387',
  red: '#f38ba8',
} as const;

let registered = false;

/** Registers the dagre layout once. Returns the cytoscape factory. */
export function getCytoscape(): typeof cytoscape {
  if (!registered) {
    cytoscape.use(dagre);
    registered = true;
  }
  return cytoscape;
}

export const GRAPH_STYLE: StylesheetStyle[] = [
  {
    selector: 'node',
    style: {
      shape: 'round-rectangle',
      width: 140,
      height: 52,
      'background-color': MOCHA.surface0,
      'border-width': 2,
      'border-color': MOCHA.overlay1,
      label: 'data(label)',
      color: MOCHA.text,
      // 15px at fit is about 12px on screen (spec 10.3). Labels wrap to two lines rather than cut off.
      'font-size': 15,
      'font-family': 'system-ui, sans-serif',
      'text-valign': 'center',
      'text-halign': 'center',
      'text-wrap': 'wrap',
      'text-max-width': '124px',
      'line-height': 1.15,
    },
  },
  { selector: 'node.kind-question', style: { 'border-color': MOCHA.lavender } },
  { selector: 'node.kind-bubble', style: { shape: 'ellipse', 'border-color': MOCHA.teal } },
  { selector: 'node.kind-cite', style: { shape: 'rectangle', 'border-color': MOCHA.sky } },
  {
    // Wide enough for "news: 4 entities and chunks" on one line (spec 10.3: friendly labels).
    selector: 'node.kind-group',
    style: {
      width: 236,
      height: 56,
      'font-size': 14,
      'text-max-width': '222px',
      'text-wrap': 'ellipsis',
      shape: 'round-rectangle',
      'background-color': MOCHA.mantle,
      'border-style': 'dashed',
      'border-color': MOCHA.overlay2,
      padding: '14px',
      'text-valign': 'top',
      'text-margin-y': -4,
    },
  },
  {
    selector: 'node.kind-entity',
    style: {
      shape: 'ellipse',
      width: 124,
      height: 44,
      'border-color': MOCHA.subtext0,
      'font-size': 13,
      'text-max-width': '104px',
    },
  },
  { selector: 'node.status-ok', style: { 'border-color': MOCHA.green } },
  { selector: 'node.status-error', style: { 'border-color': MOCHA.red, 'border-style': 'dashed' } },
  { selector: 'node.status-cancelled', style: { 'border-color': MOCHA.peach } },
  { selector: 'node.status-running', style: { 'border-color': MOCHA.lavender } },
  // Dimmed nodes keep a 4.6:1 outline (overlay1 on mantle) so they stay visible (WCAG 1.4.11).
  {
    selector: 'node.dimmed',
    style: {
      'background-color': MOCHA.mantle,
      'border-color': MOCHA.overlay1,
      color: MOCHA.subtext0,
    },
  },
  {
    selector: 'node.path',
    style: { 'border-width': 3, 'background-color': MOCHA.surface1 },
  },
  {
    selector: 'node.active',
    style: { 'border-width': 4, 'border-color': MOCHA.lavender },
  },
  { selector: 'node.pulse', style: { 'border-width': 6, 'border-color': MOCHA.lavender } },
  {
    selector: 'edge',
    // Visible but quiet: overlay1 on the mantle canvas, thin, so the nodes carry the weight.
    style: {
      width: 1.25,
      opacity: 0.85,
      'line-color': MOCHA.overlay1,
      'target-arrow-color': MOCHA.overlay1,
      'target-arrow-shape': 'triangle',
      'curve-style': 'bezier',
    },
  },
  { selector: 'edge.dimmed', style: { 'line-style': 'dashed', 'line-color': MOCHA.overlay0, opacity: 0.6 } },
  {
    selector: 'edge.path',
    style: { width: 2.5, 'line-color': MOCHA.lavender, 'target-arrow-color': MOCHA.lavender },
  },
];
