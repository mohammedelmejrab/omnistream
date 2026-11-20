import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Link } from 'react-router';
import { getGraph } from '../api/graph';
import { usePrefersReducedMotion } from '../hooks/useMediaQuery';
import type { GraphEdgeDto, GraphNodeDto } from '../trace/types';
import { globalDetail } from './detail';
import { DetailPanel } from './DetailPanel';
import { GraphCanvas, type GraphCanvasHandle } from './GraphCanvas';
import { buildGlobalGraph, GRAPH_PAGE_SIZE, toElements, type GNode } from './model';
import { NodeList } from './NodeList';
import { ZoomControls } from './ZoomControls';
import './graph.css';

// Global graph viewer at /app/graph (spec 10.5). Read-only. Filter by bubble and kind,
// search by name, load more in pages of 300, and show counts per bubble.

interface LoadedGraph {
  nodes: GraphNodeDto[];
  edges: GraphEdgeDto[];
  total: number;
}

const EMPTY: LoadedGraph = { nodes: [], edges: [], total: 0 };

export function GraphPage() {
  const reducedMotion = usePrefersReducedMotion();
  const canvasRef = useRef<GraphCanvasHandle>(null);
  const stageRef = useRef<HTMLDivElement | null>(null);
  const returnFocus = useRef<HTMLElement | null>(null);

  const [bubble, setBubble] = useState('');
  const [kind, setKind] = useState('');
  const [query, setQuery] = useState('');
  const [graph, setGraph] = useState<LoadedGraph>(EMPTY);
  const [known, setKnown] = useState<string[]>([]);
  const [phase, setPhase] = useState<'loading' | 'ready' | 'error'>('loading');
  const [loadingMore, setLoadingMore] = useState(false);
  const [focusId, setFocusId] = useState<string | null>(null);
  const [detailId, setDetailId] = useState<string | null>(null);

  // First page for the chosen bubble. Aborts the previous request on change.
  useEffect(() => {
    const ctrl = new AbortController();
    setPhase('loading');
    setDetailId(null);
    getGraph({ bubble, limit: GRAPH_PAGE_SIZE, offset: 0 }, ctrl.signal)
      .then((res) => {
        setGraph({ nodes: res.nodes, edges: res.edges, total: res.total });
        setKnown((prev) => mergeBubbles(prev, res.nodes));
        setPhase('ready');
      })
      .catch(() => {
        if (ctrl.signal.aborted) return;
        setGraph(EMPTY);
        setPhase('error');
      });
    return () => ctrl.abort();
  }, [bubble]);

  const loadMore = useCallback(async () => {
    setLoadingMore(true);
    try {
      const res = await getGraph({ bubble, limit: GRAPH_PAGE_SIZE, offset: graph.nodes.length });
      setGraph((prev) => ({
        nodes: dedupeById([...prev.nodes, ...res.nodes]),
        edges: dedupeById([...prev.edges, ...res.edges]),
        total: res.total,
      }));
      setKnown((prev) => mergeBubbles(prev, res.nodes));
    } catch {
      setPhase('error');
    } finally {
      setLoadingMore(false);
    }
  }, [bubble, graph.nodes.length]);

  const kinds = useMemo(() => [...new Set(graph.nodes.map((n) => n.kind))].sort(), [graph.nodes]);
  const visibleNodes = useMemo(
    () => graph.nodes.filter((n) => !kind || n.kind === kind),
    [graph.nodes, kind],
  );
  const visibleIds = useMemo(() => new Set(visibleNodes.map((n) => n.id)), [visibleNodes]);
  const visibleEdges = useMemo(
    () => graph.edges.filter((e) => visibleIds.has(e.source) && visibleIds.has(e.target)),
    [graph.edges, visibleIds],
  );

  const needle = query.trim().toLowerCase();
  const matchIds = useMemo(
    () =>
      needle ? new Set(visibleNodes.filter((n) => n.label.toLowerCase().includes(needle)).map((n) => n.id)) : null,
    [needle, visibleNodes],
  );

  const model = useMemo(
    () => buildGlobalGraph({ nodes: visibleNodes, edges: visibleEdges, total: graph.total }),
    [visibleNodes, visibleEdges, graph.total],
  );
  const elements = useMemo(() => toElements(model, { focus: matchIds }), [model, matchIds]);
  const nodeById = useMemo(() => new Map(model.nodes.map((n) => [n.id, n] as const)), [model]);

  const listNodes: GNode[] = useMemo(
    () => (matchIds ? model.nodes.filter((n) => matchIds.has(n.id)) : model.nodes),
    [model, matchIds],
  );
  const listItems = useMemo(
    () => listNodes.map((n) => ({ id: n.id, label: n.label, meta: n.apiKind ?? 'Node' })),
    [listNodes],
  );

  const perBubble = useMemo(() => countByBubble(graph.nodes), [graph.nodes]);
  const detail = detailId ? globalDetail(nodeById.get(detailId)) : null;

  const openDetail = (id: string) => {
    if (detailId === null) {
      const active = document.activeElement;
      returnFocus.current =
        active instanceof HTMLElement && active !== document.body ? active : stageRef.current;
    }
    setFocusId(id);
    setDetailId(id);
  };
  const closeDetail = () => {
    setDetailId(null);
    returnFocus.current?.focus();
    returnFocus.current = null;
  };

  return (
    <section className="graph-page" aria-labelledby="graph-title">
      <header className="graph-page-header">
        <h1 id="graph-title" tabIndex={-1} className="graph-title">
          Graph
        </h1>
        <p className="graph-count" role="status">
          {phase === 'ready' && graph.total > 0
            ? `Showing ${graph.nodes.length} of ${graph.total} nodes`
            : null}
        </p>
      </header>

      <div className="graph-toolbar">
        <label className="field-inline">
          Bubble
          <select value={bubble} onChange={(e) => setBubble(e.target.value)}>
            <option value="">All bubbles</option>
            {known.map((b) => (
              <option key={b} value={b}>
                {b}
              </option>
            ))}
          </select>
        </label>
        <label className="field-inline">
          Node kind
          <select value={kind} onChange={(e) => setKind(e.target.value)}>
            <option value="">All kinds</option>
            {kinds.map((k) => (
              <option key={k} value={k}>
                {k}
              </option>
            ))}
          </select>
        </label>
        <label className="field-inline">
          Search by name
          <input
            type="search"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Entity name"
          />
        </label>
        <ZoomControls
          onZoomIn={() => canvasRef.current?.zoomIn()}
          onZoomOut={() => canvasRef.current?.zoomOut()}
          onFit={() => canvasRef.current?.fit()}
        />
      </div>

      {phase === 'error' && (
        <p className="graph-error" role="alert">
          The graph could not be loaded. Check that OmniStream is running, then reload this page.
        </p>
      )}

      {phase === 'ready' && graph.total === 0 ? (
        <section className="empty-state" aria-labelledby="graph-empty-title">
          <h2 id="graph-empty-title">{bubble ? 'No nodes in this bubble yet' : 'The graph is empty'}</h2>
          <p>Add a feed, API or document to start building it.</p>
          <p>
            <Link to="/app/sources">Go to Sources</Link>
          </p>
        </section>
      ) : (
        <div className="graph-body">
          <div className="graph-stage" ref={stageRef} tabIndex={-1}>
            {phase === 'loading' ? (
              <p role="status" className="graph-loading">
                Loading graph…
              </p>
            ) : (
              <GraphCanvas
                ref={canvasRef}
                elements={elements}
                activeId={focusId}
                pulseId={null}
                reducedMotion={reducedMotion}
                label="Global graph. Use the node list beside the graph to move between nodes."
                onNodeActivate={openDetail}
              />
            )}
            {detail && <DetailPanel detail={detail} onClose={closeDetail} />}
          </div>

          <aside className="graph-side" aria-label="Graph nodes and counts">
            <h2 className="graph-side-title">Nodes</h2>
            <NodeList
              label="Graph nodes"
              items={listItems}
              activeId={focusId}
              onActiveChange={setFocusId}
              onOpen={openDetail}
            />
            <h2 className="graph-side-title">Nodes per bubble</h2>
            <ul className="bubble-counts">
              {perBubble.map(([name, count]) => (
                <li key={name}>
                  {name}: {count} loaded
                </li>
              ))}
            </ul>
            {graph.nodes.length < graph.total && (
              <button
                type="button"
                className="pill-button"
                onClick={() => void loadMore()}
                disabled={loadingMore}
              >
                {loadingMore ? 'Loading…' : `Load more (${graph.total - graph.nodes.length} left)`}
              </button>
            )}
          </aside>
        </div>
      )}
    </section>
  );
}

function dedupeById<T extends { id: string }>(items: T[]): T[] {
  const seen = new Map<string, T>();
  for (const it of items) if (!seen.has(it.id)) seen.set(it.id, it);
  return [...seen.values()];
}

function mergeBubbles(prev: string[], nodes: GraphNodeDto[]): string[] {
  const set = new Set(prev);
  for (const n of nodes) if (n.bubble) set.add(n.bubble);
  return [...set].sort();
}

function countByBubble(nodes: GraphNodeDto[]): [string, number][] {
  const counts = new Map<string, number>();
  for (const n of nodes) {
    const key = n.bubble ?? 'No bubble';
    counts.set(key, (counts.get(key) ?? 0) + 1);
  }
  return [...counts.entries()].sort((a, b) => a[0].localeCompare(b[0]));
}
