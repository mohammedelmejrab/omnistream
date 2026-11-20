import { act, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { canvasSpies } from '../graph/testing/GraphCanvasStub';
import { AGENTIC_RUN, AGENTIC_STEPS, NORMAL_RUN, NORMAL_STEPS } from './fixtures/stored-runs';
import { TracePage, VIEW_PREF_KEY } from './TracePage';
import type { Run, Step } from './types';

vi.mock('../graph/GraphCanvas', () => import('../graph/testing/GraphCanvasStub'));

// Minimal EventSource double. Tests drive it with emit() and open().
class FakeEventSource {
  static instances: FakeEventSource[] = [];
  url: string;
  onopen: (() => void) | null = null;
  onerror: (() => void) | null = null;
  closed = false;
  private listeners = new Map<string, ((ev: { data: string }) => void)[]>();
  constructor(url: string) {
    this.url = url;
    FakeEventSource.instances.push(this);
  }
  addEventListener(type: string, fn: (ev: { data: string }) => void) {
    this.listeners.set(type, [...(this.listeners.get(type) ?? []), fn]);
  }
  close() {
    this.closed = true;
  }
  emit(type: string, data: unknown) {
    (this.listeners.get(type) ?? []).forEach((fn) => fn({ data: JSON.stringify(data) }));
  }
}

interface Store {
  runs: Record<string, Run>;
  steps: Record<string, Step[]>;
}

function stubFetch(store: Store) {
  const fetchMock = vi.fn(async (input: string) => {
    const url = new URL(input, 'http://localhost');
    const m = /^\/api\/runs\/([^/]+)(\/steps)?$/.exec(url.pathname);
    if (m) {
      const id = m[1]!;
      if (m[2]) return json(200, store.steps[id] ?? []);
      const run = store.runs[id];
      if (run) return json(200, run);
    }
    return json(404, { detail: 'Not found' });
  });
  vi.stubGlobal('fetch', fetchMock);
  return fetchMock;
}

function json(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/app/trace/:runId" element={<TracePage />} />
        <Route path="/app" element={<p>Home</p>} />
      </Routes>
    </MemoryRouter>,
  );
}

function setReducedMotion(matches: boolean) {
  window.matchMedia = (query: string): MediaQueryList =>
      ({
        matches: matches && query.includes('reduce'),
        media: query,
        addEventListener: () => undefined,
        removeEventListener: () => undefined,
        addListener: () => undefined,
        removeListener: () => undefined,
        onchange: null,
        dispatchEvent: () => false,
      }) as MediaQueryList;
}

beforeEach(() => {
  FakeEventSource.instances = [];
  vi.stubGlobal('EventSource', FakeEventSource);
  setReducedMotion(false);
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('TracePage, simple view for a stored run', () => {
  beforeEach(() => {
    stubFetch({
      runs: { [NORMAL_RUN.id]: NORMAL_RUN },
      steps: { [NORMAL_RUN.id]: NORMAL_STEPS },
    });
  });

  it('opens on the four-stage view with the answer and a Normal badge', async () => {
    renderAt(`/app/trace/${NORMAL_RUN.id}`);
    expect(await screen.findByText(NORMAL_RUN.answer!)).toBeInTheDocument();
    const stages = screen.getByRole('list', { name: 'Trace stages' });
    const titles = within(stages)
      .getAllByRole('heading', { level: 3 })
      .map((h) => h.textContent?.replace(/^\d+/, '').trim());
    expect(titles).toEqual([
      'Understood your question',
      'Searched bubbles',
      'Gathered evidence',
      'Wrote answer',
    ]);
    expect(screen.getByText('Normal')).toBeInTheDocument();
    expect(within(stages).getAllByText('Done')).toHaveLength(4);
  });

  it('lists cited sources as numbered links that open in a new tab', async () => {
    renderAt(`/app/trace/${NORMAL_RUN.id}`);
    const link = await screen.findByRole('link', { name: /Gas prices rose in March/ });
    expect(link).toHaveAttribute('href', 'https://example.org/gas-prices');
    expect(link).toHaveAttribute('target', '_blank');
    expect(link).toHaveAttribute('rel', 'noopener noreferrer');
  });

  it('replay: pause, step forward, and the stage highlight moves', async () => {
    const user = userEvent.setup();
    renderAt(`/app/trace/${NORMAL_RUN.id}`);
    await screen.findByText(NORMAL_RUN.answer!);
    await user.click(screen.getByRole('button', { name: 'Replay' }));
    await user.click(screen.getByRole('button', { name: 'Pause' }));
    expect(screen.getByText('Step 0 of 5')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Step forward' }));
    expect(screen.getByText('Step 1 of 5')).toBeInTheDocument();
    const stages = screen.getByRole('list', { name: 'Trace stages' });
    const items = Array.from(stages.children);
    expect(items[0]).toHaveAttribute('aria-current', 'step');
    expect(items[1]).not.toHaveAttribute('aria-current');
  });

  it('under reduced motion, Play shows the whole run at once', async () => {
    setReducedMotion(true);
    const user = userEvent.setup();
    renderAt(`/app/trace/${NORMAL_RUN.id}`);
    await screen.findByText(NORMAL_RUN.answer!);
    await user.click(screen.getByRole('button', { name: 'Replay' }));
    expect(screen.getByRole('button', { name: 'Show all steps' })).toBeInTheDocument();
    expect(screen.getByText('Step 5 of 5')).toBeInTheDocument();
  });

  it('Advanced toggle switches to the graph and remembers the choice', async () => {
    const user = userEvent.setup();
    renderAt(`/app/trace/${NORMAL_RUN.id}`);
    await screen.findByText(NORMAL_RUN.answer!);
    const toggle = screen.getByRole('button', { name: 'Advanced' });
    expect(toggle).toHaveAttribute('aria-pressed', 'false');
    await user.click(toggle);
    expect(await screen.findByTestId('graph-canvas')).toBeInTheDocument();
    expect(toggle).toHaveAttribute('aria-pressed', 'true');
    expect(window.localStorage.getItem(VIEW_PREF_KEY)).toBe('advanced');
  });

  it('a 404 shows the not-found page with focus on its heading', async () => {
    renderAt('/app/trace/no-such-run');
    const heading = await screen.findByRole('heading', { name: 'Trace not found' });
    await waitFor(() => expect(heading).toHaveFocus());
    expect(screen.getByRole('link', { name: 'Back to chat' })).toHaveAttribute('href', '/app');
  });
});

describe('TracePage, advanced view keyboard path', () => {
  beforeEach(() => {
    stubFetch({
      runs: { [NORMAL_RUN.id]: NORMAL_RUN },
      steps: { [NORMAL_RUN.id]: NORMAL_STEPS },
    });
  });

  it('arrow keys move through the node list, Enter opens the panel, Esc returns focus', async () => {
    const user = userEvent.setup();
    renderAt(`/app/trace/${NORMAL_RUN.id}?view=advanced`);
    await screen.findByTestId('graph-canvas');
    const list = screen.getByRole('listbox', { name: 'Steps and items in this run' });
    const options = within(list).getAllByRole('option');
    expect(options.length).toBeGreaterThan(3);

    options[0]!.focus();
    await user.keyboard('{ArrowDown}');
    expect(options[1]).toHaveFocus();
    expect(options[1]).toHaveAttribute('tabindex', '0');
    expect(options[0]).toHaveAttribute('tabindex', '-1');

    await user.keyboard('{End}');
    expect(options[options.length - 1]).toHaveFocus();
    await user.keyboard('{Home}');
    expect(options[0]).toHaveFocus();

    const retrieve = options.find((o) => o.textContent?.includes('Searched Energy'))!;
    retrieve.focus();
    await user.keyboard('{Enter}');
    const panel = await screen.findByRole('complementary', { name: 'Searched Energy' });
    await waitFor(() => expect(panel).toHaveFocus());
    expect(within(panel).getByText('Internal step: retrieve')).toBeInTheDocument();
    expect(within(panel).getByText('Items touched').nextElementSibling).toHaveTextContent('4');

    await user.keyboard('{Escape}');
    expect(screen.queryByRole('complementary', { name: 'Searched Energy' })).not.toBeInTheDocument();
    expect(retrieve).toHaveFocus();
  });

  it('zoom and fit buttons call the canvas without any dragging', async () => {
    const user = userEvent.setup();
    const zoomIn = vi.spyOn(canvasSpies, 'zoomIn');
    const zoomOut = vi.spyOn(canvasSpies, 'zoomOut');
    const fit = vi.spyOn(canvasSpies, 'fit');
    renderAt(`/app/trace/${NORMAL_RUN.id}?view=advanced`);
    await screen.findByTestId('graph-canvas');
    await user.click(screen.getByRole('button', { name: 'Zoom in' }));
    await user.click(screen.getByRole('button', { name: 'Zoom out' }));
    await user.click(screen.getByRole('button', { name: 'Fit' }));
    expect(zoomIn).toHaveBeenCalledTimes(1);
    expect(zoomOut).toHaveBeenCalledTimes(1);
    expect(fit).toHaveBeenCalledTimes(1);
  });

  it('the group count expands and collapses entities from the panel', async () => {
    const user = userEvent.setup();
    renderAt(`/app/trace/${NORMAL_RUN.id}?view=advanced`);
    await screen.findByTestId('graph-canvas');
    const list = screen.getByRole('listbox', { name: 'Steps and items in this run' });
    const group = within(list)
      .getAllByRole('option')
      .find((o) => o.textContent?.includes('4 entities and chunks'))!;
    group.focus();
    await user.keyboard('{Enter}');
    const toggle = await screen.findByRole('button', { name: 'Expand entities and chunks' });
    await user.click(toggle);
    expect(screen.getByRole('button', { name: 'Collapse entities and chunks' })).toHaveAttribute(
      'aria-expanded',
      'true',
    );
  });
});

describe('TracePage, agentic run with a failed bubble', () => {
  beforeEach(() => {
    stubFetch({
      runs: { [AGENTIC_RUN.id]: AGENTIC_RUN },
      steps: { [AGENTIC_RUN.id]: AGENTIC_STEPS },
    });
  });

  it('shows the failed bubble in plain words and still shows the rest of the run', async () => {
    renderAt(`/app/trace/${AGENTIC_RUN.id}`);
    expect(await screen.findByText(AGENTIC_RUN.answer!)).toBeInTheDocument();
    expect(screen.getByText('Policy bubble could not answer')).toBeInTheDocument();
    expect(screen.getByText('Agentic')).toBeInTheDocument();
  });
});

describe('TracePage, failed and interrupted runs', () => {
  it('a failed run keeps completed steps and shows the failure as an alert', async () => {
    const failed: Run = { ...NORMAL_RUN, status: 'failed', answer: null, error: 'Rate limited by provider' };
    stubFetch({
      runs: { [failed.id]: failed },
      steps: { [failed.id]: NORMAL_STEPS.slice(0, 3) },
    });
    renderAt(`/app/trace/${failed.id}`);
    expect(await screen.findByRole('alert')).toHaveTextContent('Rate limited by provider');
    // The stage legend repeats the stage names, so look inside the stage list.
    const stages = screen.getByRole('list', { name: 'Trace stages' });
    expect(within(stages).getByText('Understood your question')).toBeInTheDocument();
    expect(screen.getByText('Could not finish')).toBeInTheDocument();
  });

  it('an interrupted run says it was interrupted by a restart', async () => {
    const interrupted: Run = { ...NORMAL_RUN, status: 'interrupted', answer: null, error: null };
    stubFetch({ runs: { [interrupted.id]: interrupted }, steps: { [interrupted.id]: NORMAL_STEPS.slice(0, 2) } });
    renderAt(`/app/trace/${interrupted.id}`);
    expect(await screen.findByText('Interrupted when OmniStream restarted')).toBeInTheDocument();
  });

  it('an empty answer from a finished run offers a retry from the chat', async () => {
    const empty: Run = { ...NORMAL_RUN, answer: null };
    stubFetch({ runs: { [empty.id]: empty }, steps: { [empty.id]: NORMAL_STEPS } });
    renderAt(`/app/trace/${empty.id}`);
    expect(await screen.findByText('The model returned no answer.')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Retry from the chat' })).toHaveAttribute(
      'href',
      `/app/chat/${NORMAL_RUN.chat_id}`,
    );
  });
});

describe('TracePage, live run', () => {
  it('streams steps in, announces each stage in words, and settles on the answer', async () => {
    const running: Run = { ...NORMAL_RUN, status: 'running', answer: null, finished_at: null };
    const store: Store = {
      runs: { [running.id]: running },
      steps: { [running.id]: NORMAL_STEPS.slice(0, 2) },
    };
    stubFetch(store);
    renderAt(`/app/trace/${running.id}`);

    await waitFor(() => expect(FakeEventSource.instances).toHaveLength(1));
    const es = FakeEventSource.instances[0]!;
    expect(es.url).toBe(`/api/runs/${running.id}/events`);
    act(() => es.onopen?.());

    const retrieve = NORMAL_STEPS[2]!;
    act(() => es.emit('step', { ...retrieve, status: 'running', duration_ms: null }));
    const polite = document.querySelector('[aria-live="polite"]');
    await waitFor(() => expect(polite).toHaveTextContent('Searching Energy bubble, step 3'));
    expect(polite).not.toHaveTextContent(' of ');

    act(() => es.emit('step', retrieve));
    act(() => es.emit('step', NORMAL_STEPS[3]!));
    act(() => es.emit('step', NORMAL_STEPS[4]!));
    // The catch-up fetch after 'done' must see the finished run.
    store.runs[running.id] = NORMAL_RUN;
    store.steps[running.id] = NORMAL_STEPS;
    act(() => es.emit('run', { ...NORMAL_RUN }));
    act(() => es.emit('done', {}));

    expect(await screen.findByText(NORMAL_RUN.answer!)).toBeInTheDocument();
    expect(es.closed).toBe(true);
  });

  it('a failing step raises an alert as it happens', async () => {
    const running: Run = { ...NORMAL_RUN, status: 'running', answer: null, finished_at: null };
    stubFetch({ runs: { [running.id]: running }, steps: { [running.id]: [] } });
    renderAt(`/app/trace/${running.id}`);
    await waitFor(() => expect(FakeEventSource.instances).toHaveLength(1));
    const es = FakeEventSource.instances[0]!;
    act(() => es.onopen?.());
    act(() =>
      es.emit('step', {
        ...AGENTIC_STEPS[3]!,
        run_id: running.id,
        status: 'error',
      }),
    );
    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent('Policy bubble could not answer');
  });

  it('a dropped connection shows a reconnecting note', async () => {
    const running: Run = { ...NORMAL_RUN, status: 'running', answer: null, finished_at: null };
    stubFetch({ runs: { [running.id]: running }, steps: { [running.id]: [] } });
    renderAt(`/app/trace/${running.id}`);
    await waitFor(() => expect(FakeEventSource.instances).toHaveLength(1));
    const es = FakeEventSource.instances[0]!;
    act(() => es.onopen?.());
    act(() => es.onerror?.());
    expect(await screen.findByText(/Connection lost/)).toBeInTheDocument();
  });
});

describe('TracePage, the no-steps case', () => {
  it('a finished run with no steps says so', async () => {
    stubFetch({ runs: { [NORMAL_RUN.id]: NORMAL_RUN }, steps: { [NORMAL_RUN.id]: [] } });
    renderAt(`/app/trace/${NORMAL_RUN.id}`);
    expect(await screen.findByText('No steps were recorded for this run.')).toBeInTheDocument();
  });
});
