import { useEffect, useState } from 'react';
import { ApiError, API_BASE } from '../api/client';
import { getRun, getRunSteps } from '../api/runs';
import { mergeStep, mergeSteps } from './model';
import type { Run, RunStatus, Step } from './types';

export function eventsUrl(runId: string): string {
  return `${API_BASE}/runs/${encodeURIComponent(runId)}/events`;
}

// Live trace for one run (spec 10.4). Events come over SSE; the client reconnects
// with backoff and, on every (re)connect, fetches stored steps to catch up.
// The controller is plain TypeScript with injected I/O so it can be tested directly.

export type ConnectionState = 'connecting' | 'live' | 'reconnecting' | 'closed';
export type LoadError = 'not-found' | 'expired' | null;

export interface StreamState {
  run: Run | null;
  steps: Step[];
  connection: ConnectionState;
  loadError: LoadError;
  loaded: boolean;
}

export const INITIAL_STREAM_STATE: StreamState = {
  run: null,
  steps: [],
  connection: 'connecting',
  loadError: null,
  loaded: false,
};

/** Reconnect delays in ms; the last value repeats. */
export const BACKOFF_MS: readonly number[] = [1000, 2000, 4000, 8000, 10000];

export function backoffDelay(attempt: number): number {
  const index = Math.min(Math.max(attempt, 0), BACKOFF_MS.length - 1);
  return BACKOFF_MS[index] ?? 10000;
}

export interface StreamHandle {
  close(): void;
}

export interface StreamHandlers {
  onOpen(): void;
  onStep(step: Step): void;
  onRun(run: Run): void;
  onDone(): void;
  onError(): void;
}

export interface StreamDeps {
  getRun(runId: string, signal?: AbortSignal): Promise<Run>;
  getSteps(runId: string, signal?: AbortSignal): Promise<Step[]>;
  open(url: string, handlers: StreamHandlers): StreamHandle;
  setTimer(fn: () => void, ms: number): unknown;
  clearTimer(handle: unknown): void;
}

export const defaultStreamDeps: StreamDeps = {
  getRun,
  getSteps: getRunSteps,
  open(url, h) {
    const es = new EventSource(url);
    es.onopen = () => h.onOpen();
    es.addEventListener('step', (ev) => h.onStep(JSON.parse((ev as MessageEvent).data) as Step));
    es.addEventListener('run', (ev) => h.onRun(JSON.parse((ev as MessageEvent).data) as Run));
    es.addEventListener('done', () => h.onDone());
    es.onerror = () => h.onError();
    return { close: () => es.close() };
  },
  setTimer: (fn, ms) => setTimeout(fn, ms),
  clearTimer: (handle) => clearTimeout(handle as ReturnType<typeof setTimeout>),
};

const RUN_RANK: Record<RunStatus, number> = {
  running: 0,
  ok: 1,
  failed: 1,
  cancelled: 1,
  interrupted: 1,
};

/** Run status only moves forward, same rule as steps. */
export function mergeRun(existing: Run | null, incoming: Run): Run {
  if (!existing) return incoming;
  if (RUN_RANK[existing.status] > 0 && RUN_RANK[incoming.status] === 0) return existing;
  return incoming;
}

type SnapshotResult = 'running' | 'done' | 'missing' | 'error';

export class RunStreamController {
  private state: StreamState = INITIAL_STREAM_STATE;
  private stream: StreamHandle | null = null;
  private retryTimer: unknown = null;
  private attempt = 0;
  private disposed = false;
  private readonly abort = new AbortController();

  constructor(
    private readonly runId: string,
    private readonly deps: StreamDeps,
    private readonly emit: (state: StreamState) => void,
  ) {}

  getState(): StreamState {
    return this.state;
  }

  start(): void {
    void this.begin();
  }

  dispose(): void {
    this.disposed = true;
    this.abort.abort();
    this.closeStream();
    if (this.retryTimer !== null) {
      this.deps.clearTimer(this.retryTimer);
      this.retryTimer = null;
    }
  }

  private set(patch: Partial<StreamState>): void {
    if (this.disposed) return;
    this.state = { ...this.state, ...patch };
    this.emit(this.state);
  }

  private closeStream(): void {
    this.stream?.close();
    this.stream = null;
  }

  /** Fetch the run and stored steps; decide whether to stream. */
  private async begin(): Promise<void> {
    const result = await this.snapshot();
    if (this.disposed) return;
    switch (result) {
      case 'running':
        this.connect();
        return;
      case 'done':
      case 'missing':
        this.closeStream();
        this.set({ connection: 'closed' });
        return;
      case 'error':
        this.set({ connection: 'reconnecting' });
        this.scheduleRetry(() => void this.begin());
    }
  }

  /** Merge the stored run and steps into state. Used for catch-up and reconnects. */
  private async snapshot(): Promise<SnapshotResult> {
    try {
      const [run, steps] = await Promise.all([
        this.deps.getRun(this.runId, this.abort.signal),
        this.deps.getSteps(this.runId, this.abort.signal),
      ]);
      if (this.disposed) return 'error';
      this.set({
        run: mergeRun(this.state.run, run),
        steps: mergeSteps(this.state.steps, steps),
        loaded: true,
        loadError: null,
      });
      return run.status === 'running' ? 'running' : 'done';
    } catch (err) {
      if (this.disposed) return 'error';
      if (err instanceof ApiError && err.status === 404) {
        this.set({ loadError: 'not-found', loaded: true });
        return 'missing';
      }
      if (err instanceof ApiError && err.status === 410) {
        this.set({ loadError: 'expired', loaded: true });
        return 'missing';
      }
      return 'error';
    }
  }

  private connect(): void {
    if (this.disposed) return;
    this.closeStream();
    this.set({ connection: 'connecting' });
    this.stream = this.deps.open(eventsUrl(this.runId), {
      onOpen: () => this.handleOpen(),
      onStep: (step) => this.set({ steps: mergeStep(this.state.steps, step) }),
      onRun: (run) => this.handleRun(run),
      onDone: () => this.handleDone(),
      onError: () => this.handleStreamError(),
    });
  }

  private handleOpen(): void {
    this.attempt = 0;
    this.set({ connection: 'live' });
    // Catch up on anything missed while disconnected. The stream stays open
    // unless the run turned out to be finished.
    void this.snapshot().then((result) => {
      if (this.disposed) return;
      if (result === 'done' || result === 'missing') {
        this.closeStream();
        this.set({ connection: 'closed' });
      }
    });
  }

  private handleRun(run: Run): void {
    this.set({ run: mergeRun(this.state.run, run) });
  }

  private handleDone(): void {
    this.closeStream();
    void this.snapshot().then(() => this.set({ connection: 'closed' }));
  }

  private handleStreamError(): void {
    if (this.disposed) return;
    this.closeStream();
    // Terminal runs do not need a stream, so an error after finish is not a retry case.
    if (this.state.run && this.state.run.status !== 'running') {
      this.set({ connection: 'closed' });
      return;
    }
    this.set({ connection: 'reconnecting' });
    this.scheduleRetry(() => void this.begin());
  }

  private scheduleRetry(fn: () => void): void {
    if (this.disposed) return;
    if (this.retryTimer !== null) this.deps.clearTimer(this.retryTimer);
    const delay = backoffDelay(this.attempt);
    this.attempt += 1;
    this.retryTimer = this.deps.setTimer(() => {
      this.retryTimer = null;
      fn();
    }, delay);
  }
}

export function useRunStream(runId: string, deps: StreamDeps = defaultStreamDeps): StreamState {
  const [state, setState] = useState<StreamState>(INITIAL_STREAM_STATE);
  useEffect(() => {
    setState(INITIAL_STREAM_STATE);
    const controller = new RunStreamController(runId, deps, setState);
    controller.start();
    return () => controller.dispose();
  }, [runId, deps]);
  return state;
}
