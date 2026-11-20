import { describe, expect, it, vi } from 'vitest';
import { ApiError } from '../api/client';
import type { Run, Step } from '../api/types';
import { AGENTIC_RUN, AGENTIC_STEPS, NORMAL_RUN, NORMAL_STEPS } from './fixtures/stored-runs';
import { buildSimpleView, orderSteps } from './model';
import {
  backoffDelay,
  INITIAL_STREAM_STATE,
  RunStreamController,
  type StreamDeps,
  type StreamHandlers,
  type StreamState,
} from './stream';

interface FakeStream {
  handlers: StreamHandlers;
  closed: boolean;
}

interface FakeTimer {
  id: number;
  ms: number;
  fn: () => void;
}

function harness(initial: { run: Run; steps: Step[] }) {
  let run: Run = initial.run;
  let steps: Step[] = initial.steps;
  let getRunError: unknown = null;
  let getStepsError: unknown = null;
  const streams: FakeStream[] = [];
  let timers: FakeTimer[] = [];
  let nextId = 1;
  const states: StreamState[] = [];

  const deps: StreamDeps = {
    getRun: vi.fn(async () => {
      if (getRunError) throw getRunError;
      return run;
    }),
    getSteps: vi.fn(async () => {
      if (getStepsError) throw getStepsError;
      return steps;
    }),
    open(_url, handlers) {
      const s: FakeStream = { handlers, closed: false };
      streams.push(s);
      return {
        close() {
          s.closed = true;
        },
      };
    },
    setTimer(fn, ms) {
      const id = nextId++;
      timers.push({ id, ms, fn });
      return id;
    },
    clearTimer(handle) {
      timers = timers.filter((t) => t.id !== handle);
    },
  };

  const controller = new RunStreamController('run-x', deps, (s) => states.push(s));
  const flush = () => new Promise<void>((resolve) => setTimeout(resolve, 0));
  const latest = () => states[states.length - 1] ?? INITIAL_STREAM_STATE;
  const live = () => streams.filter((s) => !s.closed);

  return {
    controller,
    deps,
    streams,
    states,
    flush,
    latest,
    live,
    timers: () => timers,
    setRun(next: Run) {
      run = next;
    },
    setSteps(next: Step[]) {
      steps = next;
    },
    failRun(err: unknown) {
      getRunError = err;
    },
    failSteps(err: unknown) {
      getStepsError = err;
    },
    fireTimers() {
      const due = timers;
      timers = [];
      due.forEach((t) => t.fn());
    },
  };
}

const RUNNING: Run = { ...NORMAL_RUN, status: 'running', answer: null, finished_at: null };

describe('RunStreamController, stored runs', () => {
  it('loads a finished run from stored steps and does not open a stream', async () => {
    const h = harness({ run: NORMAL_RUN, steps: NORMAL_STEPS });
    h.controller.start();
    await h.flush();
    expect(h.streams).toHaveLength(0);
    expect(h.latest()).toMatchObject({ loaded: true, connection: 'closed', loadError: null });
    expect(h.latest().steps.map((s) => s.id)).toEqual(NORMAL_STEPS.map((s) => s.id));
  });

  it('an unknown run (404) reports not-found and opens nothing', async () => {
    const h = harness({ run: NORMAL_RUN, steps: [] });
    h.failRun(new ApiError(404, 'missing'));
    h.controller.start();
    await h.flush();
    expect(h.latest()).toMatchObject({ loadError: 'not-found', loaded: true, connection: 'closed' });
    expect(h.streams).toHaveLength(0);
    expect(h.timers()).toHaveLength(0);
  });

  it('an expired run (410) reports expired', async () => {
    const h = harness({ run: NORMAL_RUN, steps: [] });
    h.failRun(new ApiError(410, 'gone'));
    h.controller.start();
    await h.flush();
    expect(h.latest().loadError).toBe('expired');
  });
});

describe('RunStreamController, live runs', () => {
  it('opens the stream for a running run and applies step and run events', async () => {
    const h = harness({ run: RUNNING, steps: NORMAL_STEPS.slice(0, 2) });
    h.controller.start();
    await h.flush();
    expect(h.streams).toHaveLength(1);
    const stream = h.streams[0]!;

    stream.handlers.onOpen();
    await h.flush();
    expect(h.latest().connection).toBe('live');

    // A step starts (running copy), then finishes.
    const retrieve = NORMAL_STEPS[2]!;
    stream.handlers.onStep({ ...retrieve, status: 'running', duration_ms: null });
    expect(h.latest().steps.find((s) => s.id === 'n-retrieve')?.status).toBe('running');
    stream.handlers.onStep(retrieve);
    expect(h.latest().steps.find((s) => s.id === 'n-retrieve')?.status).toBe('ok');

    stream.handlers.onRun({ ...NORMAL_RUN });
    expect(h.latest().run?.status).toBe('ok');

    stream.handlers.onDone();
    await h.flush();
    expect(stream.closed).toBe(true);
    expect(h.latest().connection).toBe('closed');
  });

  it('after a drop, reconnects with backoff and catches up on missed steps', async () => {
    const h = harness({ run: RUNNING, steps: NORMAL_STEPS.slice(0, 1) });
    h.controller.start();
    await h.flush();
    h.streams[0]!.handlers.onOpen();
    h.streams[0]!.handlers.onError();
    expect(h.latest().connection).toBe('reconnecting');
    expect(h.streams[0]!.closed).toBe(true);
    expect(h.timers()).toHaveLength(1);
    expect(h.timers()[0]!.ms).toBe(1000);

    // While disconnected the run moved on; the catch-up fetch must pick it up.
    h.setSteps(NORMAL_STEPS.slice(0, 4));
    h.fireTimers();
    await h.flush();
    expect(h.streams).toHaveLength(2);
    expect(h.latest().steps).toHaveLength(4);
    expect(h.latest().connection).toBe('connecting');
  });

  it('if the run finished during the drop, reconnect does not reopen the stream', async () => {
    const h = harness({ run: RUNNING, steps: NORMAL_STEPS.slice(0, 1) });
    h.controller.start();
    await h.flush();
    h.streams[0]!.handlers.onError();
    h.setRun(NORMAL_RUN);
    h.setSteps(NORMAL_STEPS);
    h.fireTimers();
    await h.flush();
    expect(h.streams).toHaveLength(1);
    expect(h.latest()).toMatchObject({ connection: 'closed' });
    expect(h.latest().steps).toHaveLength(NORMAL_STEPS.length);
  });

  it('a stream open that finds the run already finished closes the stream', async () => {
    const h = harness({ run: RUNNING, steps: [] });
    h.controller.start();
    await h.flush();
    h.setRun(NORMAL_RUN);
    h.setSteps(NORMAL_STEPS);
    h.streams[0]!.handlers.onOpen();
    await h.flush();
    expect(h.streams[0]!.closed).toBe(true);
    expect(h.latest().connection).toBe('closed');
  });

  it('a transient failure while fetching retries instead of giving up', async () => {
    const h = harness({ run: RUNNING, steps: [] });
    h.failRun(new TypeError('network down'));
    h.controller.start();
    await h.flush();
    expect(h.latest().connection).toBe('reconnecting');
    expect(h.streams).toHaveLength(0);
    h.failRun(null);
    h.fireTimers();
    await h.flush();
    expect(h.streams).toHaveLength(1);
  });

  it('reconnect delays grow to a 10 second cap', async () => {
    const h = harness({ run: RUNNING, steps: [] });
    h.controller.start();
    await h.flush();
    const delays: number[] = [];
    for (let i = 0; i < 6; i++) {
      h.streams[h.streams.length - 1]!.handlers.onError();
      delays.push(h.timers()[0]!.ms);
      h.fireTimers();
      await h.flush();
    }
    expect(delays).toEqual([1000, 2000, 4000, 8000, 10000, 10000]);
  });

  it('dispose closes the stream, clears the timer and stops emitting', async () => {
    const h = harness({ run: RUNNING, steps: [] });
    h.controller.start();
    await h.flush();
    h.streams[0]!.handlers.onError();
    expect(h.timers()).toHaveLength(1);
    const before = h.states.length;
    h.controller.dispose();
    expect(h.timers()).toHaveLength(0);
    h.streams[0]!.handlers.onOpen();
    await h.flush();
    expect(h.states.length).toBe(before);
  });

  it('backoff delays repeat the last value after the table ends', () => {
    expect([0, 1, 2, 3, 4, 5, 9].map(backoffDelay)).toEqual([1000, 2000, 4000, 8000, 10000, 10000, 10000]);
  });
});

describe('replay matches live', () => {
  it('the steps built from live events equal the stored steps, and render the same view', async () => {
    // Stored run: what the server will return once finished.
    const stored = AGENTIC_STEPS;
    const h = harness({ run: { ...AGENTIC_RUN, status: 'running', answer: null }, steps: stored.slice(0, 1) });
    h.controller.start();
    await h.flush();
    const stream = h.streams[0]!;
    stream.handlers.onOpen();
    await h.flush();

    // Live events: each step starts (running copy) then finishes, in order.
    for (const step of stored.slice(1)) {
      stream.handlers.onStep({ ...step, status: 'running', duration_ms: null, error: null });
      stream.handlers.onStep(step);
    }
    stream.handlers.onRun(AGENTIC_RUN);
    stream.handlers.onDone();
    await h.flush();

    // Catch-up fetch after done returns the same stored steps.
    h.setSteps(stored);
    h.setRun(AGENTIC_RUN);
    const liveSteps = h.latest().steps;
    expect(liveSteps).toEqual(orderSteps(stored));

    const fromLive = buildSimpleView(AGENTIC_RUN, liveSteps, { complete: true });
    const fromStored = buildSimpleView(AGENTIC_RUN, stored, { complete: true });
    expect(fromLive).toEqual(fromStored);
  });
});
