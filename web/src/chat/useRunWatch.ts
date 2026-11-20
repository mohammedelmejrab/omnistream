import { useEffect, useRef, useState } from 'react';
import { NetworkError } from '@/api/client';
import type { Run, Step } from '@/api/types';
import { defaultStreamDeps, INITIAL_STREAM_STATE, RunStreamController, type StreamState } from '@/trace/stream';

export interface RunWatch {
  run: Run | undefined;
  steps: Step[];
  /** The run record or its trace no longer exists (expired after 30 days, or unknown). */
  gone: boolean;
  /** The live connection is down and retrying. */
  error: Error | undefined;
}

const EMPTY: RunWatch = { run: undefined, steps: [], gone: false, error: undefined };

function toWatch(state: StreamState): RunWatch {
  return {
    run: state.run ?? undefined,
    steps: state.steps,
    gone: state.loadError !== null,
    error: state.connection === 'reconnecting' ? new NetworkError() : undefined,
  };
}

/**
 * Follows one run over the live trace stream (spec 10.4): a snapshot first,
 * then Server-Sent Events while the run is running. Reconnects and catch-up
 * are handled by RunStreamController. `onFinish` fires once per run, the first
 * time a final status is seen.
 */
export function useRunWatch(runId: string | null, onFinish?: (run: Run) => void): RunWatch {
  const [state, setState] = useState<StreamState>(INITIAL_STREAM_STATE);
  const finishRef = useRef(onFinish);
  finishRef.current = onFinish;
  const finishedFor = useRef<string | null>(null);

  useEffect(() => {
    finishedFor.current = null;
    setState(INITIAL_STREAM_STATE);
    if (!runId) return;
    const controller = new RunStreamController(runId, defaultStreamDeps, setState);
    controller.start();
    return () => controller.dispose();
  }, [runId]);

  const run = state.run;
  useEffect(() => {
    if (!run || run.status === 'running' || finishedFor.current === run.id) return;
    finishedFor.current = run.id;
    finishRef.current?.(run);
  }, [run]);

  return runId ? toWatch(state) : EMPTY;
}
