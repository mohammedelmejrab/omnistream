import type { ReactElement } from 'react';
import { Link } from 'react-router';
import type { RunMode } from '@/api/types';
import { StatusChip } from '@/components/StatusChip';
import { AnswerBlock } from './AnswerBlock';
import { describeStep, currentStep } from './announce';
import { useRunWatch, type RunWatch } from './useRunWatch';

interface RunBlockProps {
  runId: string;
  /** The question that started this run, for Retry. */
  question: string;
  mode: RunMode;
  /** True when a stored assistant message already holds this run's answer. */
  hasAnswerMessage: boolean;
  bubbleName: (id: string) => string | null;
  /** Live watch supplied by the page for the latest run. Others poll themselves. */
  watch?: RunWatch;
  onRetry: (question: string, mode: RunMode) => void;
}

/**
 * Status of one run in the thread: live progress, the answer when no stored
 * answer exists yet, failure, stop, interruption, or an expired trace.
 */
export function RunBlock(props: RunBlockProps): ReactElement | null {
  const { runId, question, mode, hasAnswerMessage, bubbleName, onRetry } = props;
  const own = useRunWatch(props.watch ? null : runId);
  const w = props.watch ?? own;
  const run = w.run;
  const status = run?.status;
  const traceLink = (
    <Link to={`/app/trace/${runId}`} className="trace-link">
      {status === 'running' ? 'Open live trace' : 'View trace'}
    </Link>
  );

  if (w.gone && !run) {
    return (
      <div className="run-block">
        <p className="muted trace-gone">Trace no longer available</p>
      </div>
    );
  }

  if (!run) {
    if (w.error) {
      return (
        <div className="run-block">
          <p className="notice notice-warning" role="status">
            Lost connection to OmniStream. Retrying…
          </p>
        </div>
      );
    }
    return (
      <div className="run-block">
        <p className="muted" role="status">
          Starting the run…
        </p>
      </div>
    );
  }

  if (status === 'running') {
    const step = currentStep(w.steps);
    const stageText = step ? describeStep(step, bubbleName) : 'Starting';
    return (
      <div className="run-block">
        <div className="run-progress">
          <StatusChip tone="working" label="Working" />
          <span className="run-stage" aria-live="polite" aria-atomic="true">
            {stageText}
            {step ? `, step ${w.steps.length}` : ''}
          </span>
          {traceLink}
        </div>
      </div>
    );
  }

  if (status === 'ok' && run.answer && run.answer.trim()) {
    if (hasAnswerMessage) return null;
    return <AnswerBlock content={run.answer} mode={mode} runId={runId} />;
  }

  if (status === 'cancelled') {
    return (
      <div className="run-block">
        <div className="run-progress">
          <StatusChip tone="muted" label="Stopped" />
          <span className="muted">Steps finished before you stopped are kept.</span>
          {traceLink}
        </div>
      </div>
    );
  }

  if (status === 'interrupted') {
    return (
      <div className="run-block">
        <div className="run-progress">
          <StatusChip tone="warning" label="Interrupted" />
          <span>Interrupted when OmniStream restarted</span>
          {traceLink}
        </div>
      </div>
    );
  }

  // failed, or ok with an empty answer (spec 13: shown as a failed run).
  const message =
    status === 'failed' && run.error
      ? run.error
      : status === 'failed'
        ? 'The run failed.'
        : 'The model returned no answer';
  return (
    <div className="run-block">
      <div className="notice notice-error run-failure" role="alert">
        <div className="run-progress">
          <StatusChip tone="error" label="Could not finish" />
          <span>{message}</span>
        </div>
        <div className="run-actions">
          <button type="button" className="btn btn-pill" onClick={() => onRetry(question, mode)}>
            Retry
          </button>
          {traceLink}
        </div>
      </div>
    </div>
  );
}

