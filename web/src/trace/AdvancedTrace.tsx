import { useCallback, useMemo, useRef, useState } from 'react';
import { DetailPanel } from '../graph/DetailPanel';
import { nodeMeta, traceDetail } from '../graph/detail';
import { GraphCanvas, type GraphCanvasHandle } from '../graph/GraphCanvas';
import {
  answerPath,
  buildTraceGraph,
  citeNodeId,
  stepNodeId,
  toElements,
} from '../graph/model';
import { NodeList } from '../graph/NodeList';
import { ZoomControls } from '../graph/ZoomControls';
import { useMediaQuery } from '../hooks/useMediaQuery';
import { STEP_STATUS_WORD, stepLabels } from './model';
import { Timeline } from './Timeline';
import type { Step } from './types';
import '../graph/graph.css';

/** Narrow windows: the detail panel overlays the graph (spec 11.1). */
export const OVERLAY_QUERY = '(max-width: 1279px)';
/** The 360px panel plus its 16px gutter: the part of the canvas an overlay covers. */
export const PANEL_OVERLAY_INSET = 376;

// Advanced trace (spec 10.3). The graph, the keyboard list, the detail panel, zoom and fit,
// and a timeline strip. The canvas and the list read the same model.

export interface AdvancedTraceProps {
  /** Every step of the run, in order (for the timeline). */
  allSteps: Step[];
  /** Steps revealed so far by the replay cursor (for the graph). */
  revealedSteps: Step[];
  cursor: number;
  onSeek(cursor: number): void;
  reducedMotion: boolean;
}

export function AdvancedTrace({ allSteps, revealedSteps, cursor, onSeek, reducedMotion }: AdvancedTraceProps) {
  const canvasRef = useRef<GraphCanvasHandle>(null);
  // Below 1280px the detail panel overlays the graph; at 1280px and up it sits beside it.
  const overlay = useMediaQuery(OVERLAY_QUERY);
  const stageRef = useRef<HTMLDivElement | null>(null);
  const returnFocus = useRef<HTMLElement | null>(null);
  const [expanded, setExpanded] = useState<ReadonlySet<string>>(() => new Set());
  const [focusId, setFocusId] = useState<string | null>(null);
  const [detailId, setDetailId] = useState<string | null>(null);
  const [showPath, setShowPath] = useState(true);

  const model = useMemo(
    () => buildTraceGraph(revealedSteps, { expandedBubbles: expanded }),
    [revealedSteps, expanded],
  );
  const hasAnswer = revealedSteps.some((s) => s.kind === 'answer');
  const focus = useMemo(
    () => (showPath && hasAnswer ? answerPath(revealedSteps) : null),
    [showPath, hasAnswer, revealedSteps],
  );
  const elements = useMemo(() => toElements(model, { focus }), [model, focus]);
  const nodeById = useMemo(() => new Map(model.nodes.map((n) => [n.id, n] as const)), [model]);

  const runningStep = revealedSteps.find((s) => s.status === 'running');
  const pulseId = runningStep ? stepNodeId(runningStep.id) : null;

  const listItems = useMemo(
    () => model.nodes.map((n) => ({ id: n.id, label: n.label, meta: nodeMeta(n) })),
    [model],
  );

  const detail = detailId ? traceDetail(nodeById.get(detailId), revealedSteps, expanded) : null;

  const openDetail = useCallback(
    (id: string) => {
      if (detailId === null) {
        const active = document.activeElement;
        returnFocus.current =
          active instanceof HTMLElement && active !== document.body ? active : stageRef.current;
      }
      setFocusId(id);
      setDetailId(id);
    },
    [detailId],
  );

  const closeDetail = useCallback(() => {
    setDetailId(null);
    returnFocus.current?.focus();
    returnFocus.current = null;
  }, []);

  const toggleGroup = useCallback((bubble: string) => {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(bubble)) next.delete(bubble);
      else next.add(bubble);
      return next;
    });
  }, []);

  const jumpToCitation = useCallback(
    (itemId: string) => {
      const id = citeNodeId(itemId);
      setFocusId(id);
      canvasRef.current?.centerOn(id);
      openDetail(id);
    },
    [openDetail],
  );

  const selectedIndex = cursor > 0 ? cursor - 1 : -1;
  const timelineLabels = stepLabels(allSteps);
  const timelineItems = allSteps.map((s) => ({
    id: s.id,
    label: timelineLabels.get(s.id) ?? s.kind,
    durationMs: s.duration_ms,
    statusWord: STEP_STATUS_WORD[s.status],
    statusClass: `status-${s.status}`,
  }));

  return (
    <section className="advanced-trace" aria-label="Full graph">
      <div className="advanced-toolbar">
        <button
          type="button"
          className="pill-button"
          aria-pressed={showPath}
          onClick={() => setShowPath((v) => !v)}
          disabled={!hasAnswer}
        >
          Highlight answer path
        </button>
        <ZoomControls
          onZoomIn={() => canvasRef.current?.zoomIn()}
          onZoomOut={() => canvasRef.current?.zoomOut()}
          onFit={() => canvasRef.current?.fit()}
        />
      </div>

      <div className="advanced-body">
        <div className="graph-stage" ref={stageRef} tabIndex={-1}>
          <GraphCanvas
            ref={canvasRef}
            elements={elements}
            activeId={focusId}
            pulseId={pulseId}
            reducedMotion={reducedMotion}
            overlayInset={detail && overlay ? PANEL_OVERLAY_INSET : 0}
            label="Trace graph. Use the step list beside the graph to move between items."
            onNodeActivate={(id) => {
              const node = nodeById.get(id);
              if (node?.kind === 'group' && node.bubble) toggleGroup(node.bubble);
              openDetail(id);
            }}
          />
          {detail && (
            <DetailPanel
              detail={detail}
              onClose={closeDetail}
              onToggleGroup={toggleGroup}
              onJumpToCitation={jumpToCitation}
            />
          )}
        </div>

        <div className="advanced-list">
          <h3 className="advanced-list-title">Steps and items</h3>
          <NodeList
            label="Steps and items in this run"
            items={listItems}
            activeId={focusId}
            onActiveChange={setFocusId}
            onOpen={openDetail}
          />
        </div>
      </div>

      <Timeline
        label="Timeline of steps"
        items={timelineItems}
        currentIndex={selectedIndex}
        onSelect={(i) => onSeek(i + 1)}
      />
    </section>
  );
}
