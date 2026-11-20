import { lazy, Suspense, useEffect, useMemo, useRef, useState, type RefObject } from 'react';
import { Link, useParams, useSearchParams } from 'react-router';
import { announceStep, dedupeAnnouncement, failureLabel } from './announce';
import { useReplay } from './hooks';
import { usePrefersReducedMotion } from '../hooks/useMediaQuery';
import {
  buildSimpleView,
  currentStageIndex,
  failureText,
  orderSteps,
  RUN_STATUS_WORD,
  type Stage,
} from './model';
import { ReplayControls } from './ReplayControls';
import { SimpleView } from './SimpleView';
import { useRunStream } from './stream';
import type { Mode, Run, Step } from './types';
import './trace.css';

// Trace of one run at /app/trace/:runId (spec 5, 10.2 to 10.4).
// Opens on the simple four-stage view; "Advanced" (or ?view=advanced) opens the graph.

const AdvancedTrace = lazy(() =>
  import('./AdvancedTrace').then((m) => ({ default: m.AdvancedTrace })),
);

export const VIEW_PREF_KEY = 'omnistream.trace.view';

export interface TracePageProps {
  /** Overrides the route parameter. Used by tests and by the router when it passes the id in. */
  runId?: string;
}

export function TracePage(props: TracePageProps) {
  const params = useParams();
  const runId = props.runId ?? params.runId ?? params.run_id ?? '';
  return <TraceRoute key={runId} runId={runId} />;
}

function readPref(): 'simple' | 'advanced' {
  try {
    return window.localStorage.getItem(VIEW_PREF_KEY) === 'advanced' ? 'advanced' : 'simple';
  } catch {
    return 'simple';
  }
}

function writePref(view: 'simple' | 'advanced'): void {
  try {
    window.localStorage.setItem(VIEW_PREF_KEY, view);
  } catch {
    // Storage may be blocked; the choice then lasts for this page only.
  }
}

function TraceRoute({ runId }: { runId: string }) {
  const stream = useRunStream(runId);
  const reducedMotion = usePrefersReducedMotion();
  const [searchParams, setSearchParams] = useSearchParams();
  const [pref, setPref] = useState<'simple' | 'advanced'>(readPref);
  const headingRef = useRef<HTMLHeadingElement | null>(null);

  const queryView = searchParams.get('view');
  const advanced = queryView === 'advanced' ? true : queryView === 'simple' ? false : pref === 'advanced';

  const setView = (next: 'simple' | 'advanced') => {
    setPref(next);
    writePref(next);
    setSearchParams(
      (prev) => {
        const n = new URLSearchParams(prev);
        n.set('view', next);
        return n;
      },
      { replace: true },
    );
  };

  const { run, steps } = stream;
  const live = run !== null && run.status === 'running';
  const ordered = useMemo(() => orderSteps(steps), [steps]);
  const total = ordered.length;
  const { state: replay, cursor, actions } = useReplay(total, { reducedMotion });
  const revealed = useMemo(() => ordered.slice(0, cursor), [ordered, cursor]);
  const atEnd = cursor >= total;

  const placeholderRun = useMemo<Pick<Run, 'mode' | 'status'>>(
    () => ({ mode: 'normal', status: 'running' }),
    [],
  );
  const viewModel = useMemo(
    () => buildSimpleView(run ?? placeholderRun, revealed, { complete: !live && atEnd }),
    [run, placeholderRun, revealed, live, atEnd],
  );
  const currentStage = live
    ? viewModel.stages.findIndex((s) => s.status === 'working')
    : atEnd
      ? -1
      : currentStageIndex(viewModel, cursor);

  const announcements = useAnnouncements(ordered, live);

  if (stream.loadError === 'not-found') {
    return <NotFound headingRef={headingRef} />;
  }
  if (stream.loadError === 'expired') {
    return <Expired headingRef={headingRef} />;
  }
  if (!stream.loaded || run === null) {
    return (
      <section className="trace-page" aria-labelledby="trace-title">
        <h1 id="trace-title" ref={headingRef} tabIndex={-1} className="trace-title">
          Trace
        </h1>
        <p role="status" className="trace-status">
          Loading trace…
        </p>
      </section>
    );
  }

  const showAdvanced = advanced;

  return (
    <section className="trace-page" aria-labelledby="trace-title">
      <header className="trace-header">
        <div>
          <h1 id="trace-title" ref={headingRef} tabIndex={-1} className="trace-title">
            Trace
          </h1>
          <p className="trace-meta">
            <ModeBadge mode={run.mode} /> <span className="run-status">{RUN_STATUS_WORD[run.status]}</span>
            {' · '}
            <Link to={`/app/chat/${encodeURIComponent(run.chat_id)}`}>Back to chat</Link>
          </p>
        </div>
        <button
          type="button"
          className="pill-button"
          aria-pressed={showAdvanced}
          onClick={() => setView(showAdvanced ? 'simple' : 'advanced')}
        >
          Advanced
        </button>
      </header>

      <AnswerBlock run={run} complete={!live && atEnd} />

      {stream.connection === 'reconnecting' && (
        <p className="trace-note" role="status">
          Connection lost. Reconnecting and catching up…
        </p>
      )}

      <div className="sr-only" role="status" aria-live="polite">
        {announcements.polite}
      </div>
      {announcements.alert && (
        <p className="sr-only" role="alert">
          {announcements.alert}
        </p>
      )}

      {total > 0 && (
        <ReplayControls
          state={replay}
          cursor={cursor}
          actions={actions}
          total={total}
          reducedMotion={reducedMotion}
          live={live}
        />
      )}

      {showAdvanced ? (
        <Suspense fallback={<p role="status">Loading graph…</p>}>
          <AdvancedTrace
            allSteps={ordered}
            revealedSteps={revealed}
            cursor={cursor}
            onSeek={actions.seek}
            reducedMotion={reducedMotion}
          />
        </Suspense>
      ) : (
        <SimpleView
          view={viewModel}
          currentStage={currentStage}
          onSelectStage={(i) => actions.seek(stageEndCursor(viewModel.stages[i], ordered))}
        />
      )}

      {total === 0 && !live && (
        <p className="trace-note">No steps were recorded for this run.</p>
      )}
    </section>
  );
}

/** Cursor value that reveals a stage through its last step. */
export function stageEndCursor(stage: Stage | undefined, ordered: readonly { id: string }[]): number {
  if (!stage || stage.stepIds.length === 0) return 0;
  let last = -1;
  ordered.forEach((s, i) => {
    if (stage.stepIds.includes(s.id)) last = i;
  });
  return last + 1;
}

function ModeBadge({ mode }: { mode: Mode }) {
  return mode === 'agentic' ? (
    <span className="mode-badge mode-agentic">
      <span aria-hidden="true">◆</span> Agentic
    </span>
  ) : (
    <span className="mode-badge mode-normal">
      <span aria-hidden="true">●</span> Normal
    </span>
  );
}

function AnswerBlock({ run, complete }: { run: Run; complete: boolean }) {
  if (!complete) {
    return (
      <section className="answer-block" aria-label="Answer">
        <p className="answer-placeholder">
          {run.status === 'running'
            ? 'The answer appears when the run finishes.'
            : 'The answer appears at the end of the replay.'}
        </p>
      </section>
    );
  }
  if (run.answer) {
    return (
      <section className="answer-block" aria-label="Answer">
        <p className="answer-text">{run.answer}</p>
      </section>
    );
  }
  if (run.status === 'ok') {
    return (
      <section className="answer-block" aria-label="Answer">
        <p className="answer-placeholder">
          The model returned no answer.{' '}
          <Link to={`/app/chat/${encodeURIComponent(run.chat_id)}`}>Retry from the chat</Link>
        </p>
      </section>
    );
  }
  return (
    <section className="answer-block answer-failed" aria-label="Answer">
      <p className="answer-placeholder" role="alert">
        {failureText(run) ?? 'The run failed.'}
      </p>
    </section>
  );
}

function NotFound({ headingRef }: { headingRef: RefObject<HTMLHeadingElement | null> }) {
  useEffect(() => {
    headingRef.current?.focus();
  }, [headingRef]);
  return (
    <section className="trace-page" aria-labelledby="trace-title">
      <h1 id="trace-title" ref={headingRef} tabIndex={-1} className="trace-title">
        Trace not found
      </h1>
      <p>This run does not exist.</p>
      <p>
        <Link to="/app">Back to chat</Link>
      </p>
    </section>
  );
}

function Expired({ headingRef }: { headingRef: RefObject<HTMLHeadingElement | null> }) {
  useEffect(() => {
    headingRef.current?.focus();
  }, [headingRef]);
  return (
    <section className="trace-page" aria-labelledby="trace-title">
      <h1 id="trace-title" ref={headingRef} tabIndex={-1} className="trace-title">
        Trace no longer available
      </h1>
      <p>Traces are kept for 30 days. The chat still has the answer.</p>
      <p>
        <Link to="/app">Back to chat</Link>
      </p>
    </section>
  );
}

/**
 * Screen-reader text for live stages (spec 10.4). Stored runs stay silent: only steps
 * that arrive while the run is live are announced.
 */
export function useAnnouncements(
  ordered: readonly Step[],
  live: boolean,
): { polite: string; alert: string | null } {
  const seen = useRef<Set<string>>(new Set());
  const lastLabel = useRef<string | null>(null);
  const [polite, setPolite] = useState('');
  const [alert, setAlert] = useState<string | null>(null);

  useEffect(() => {
    if (!live) {
      // Finished or stored runs: remember every step, announce nothing.
      ordered.forEach((s) => seen.current.add(s.id));
      return;
    }
    let nextPolite: string | null = null;
    let nextAlert: string | null = null;
    ordered.forEach((s, i) => {
      if (seen.current.has(s.id)) return;
      seen.current.add(s.id);
      if (s.status === 'error') {
        nextAlert = failureLabel(s);
        return;
      }
      // The total is unknown while the run is live, so no "of N" here.
      const result = dedupeAnnouncement(lastLabel.current, announceStep(s, i + 1, null));
      lastLabel.current = result.last;
      if (result.announce) nextPolite = result.announce;
    });
    if (nextPolite !== null) setPolite(nextPolite);
    if (nextAlert !== null) setAlert(nextAlert);
  }, [ordered, live]);

  return { polite, alert };
}
