import { act, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { RouterProvider, createMemoryRouter } from 'react-router';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { mockApi, iso } from '@/test/api-mock';
import { ChatPage } from './ChatPage';

// Minimal EventSource double: the run page follows the live trace over SSE.
class FakeEventSource {
  static instances: FakeEventSource[] = [];
  url: string;
  onopen: (() => void) | null = null;
  onerror: (() => void) | null = null;
  closed = false;
  constructor(url: string) {
    this.url = url;
    FakeEventSource.instances.push(this);
  }
  addEventListener() {
    /* events are not needed here: the snapshot after open carries the result */
  }
  close() {
    this.closed = true;
  }
}

beforeEach(() => {
  FakeEventSource.instances = [];
  vi.stubGlobal('EventSource', FakeEventSource);
});

const chat = { id: 'c1', title: 'EU energy', mode: 'normal', created_at: iso(), updated_at: iso() };
const bubbles = [{ id: 'b1', name: 'Energy', description: '', half_life_days: 30, created_at: iso(), updated_at: iso() }];
const provider = { key_set: true, key_hint: 'a7f2', key_source: 'ui', base_url: 'https://x.test/v1', model: 'm' };

function renderChat(path = '/app/chat/c1', state?: unknown) {
  const router = createMemoryRouter(
    [
      { path: '/app/chat/:chatId', element: <ChatPage /> },
      { path: '/app/chats', element: <p>chats list</p> },
    ],
    { initialEntries: [{ pathname: path, state: state ?? null }] },
  );
  return render(<RouterProvider router={router} />);
}

describe('Chat answer loop', () => {
  it('sends a question, follows the run, and shows the answer with its mode badge', async () => {
    const user = userEvent.setup();
    let runPolls = 0;
    const messages: unknown[] = [];
    const mock = mockApi(({ method, path }) => {
      if (method === 'GET' && path === '/chats/c1') return { json: { chat, messages } };
      if (method === 'GET' && path === '/bubbles') return { json: bubbles };
      if (method === 'GET' && path === '/sources') return { json: [] };
      if (method === 'GET' && path === '/settings/provider') return { json: provider };
      if (method === 'POST' && path === '/chats/c1/messages') {
        messages.push({
          id: 'm1', chat_id: 'c1', role: 'user', content: 'What is new?', run_id: 'r1', mode: 'normal', created_at: iso(),
        });
        return { json: { run_id: 'r1' } };
      }
      if (method === 'GET' && path === '/runs/r1') {
        runPolls += 1;
        return runPolls < 2
          ? { json: { id: 'r1', chat_id: 'c1', mode: 'normal', status: 'running', answer: null, error: null, started_at: iso(), finished_at: null } }
          : { json: { id: 'r1', chat_id: 'c1', mode: 'normal', status: 'ok', answer: 'Prices rose.', error: null, started_at: iso(), finished_at: iso(5) } };
      }
      if (method === 'GET' && path === '/runs/r1/steps') {
        return { json: [{ id: 's1', run_id: 'r1', parent_step_id: null, kind: 'answer', bubble: null, started_at: iso(), duration_ms: 5, status: 'ok', summary: {}, node_ids: [], edge_ids: [], citations: [{ item_id: 'i1', url: 'https://ex.test/a', title: 'Source A' }], error: null }] };
      }
      return { status: 500, json: { detail: `unhandled ${method} ${path}` } };
    });

    renderChat();
    const box = await screen.findByRole('combobox', { name: 'Your question' });
    await user.type(box, 'What is new?');
    await user.keyboard('{Enter}');

    expect(mock.calls.find((c) => c.method === 'POST')?.body).toEqual({ content: 'What is new?', mode: 'normal' });
    // The running run is followed over SSE, not by polling.
    await waitFor(() => expect(FakeEventSource.instances).toHaveLength(1));
    expect(FakeEventSource.instances[0]?.url).toBe('/api/runs/r1/events');
    expect(runPolls).toBe(1);
    act(() => FakeEventSource.instances[0]?.onopen?.());
    expect(await screen.findByText('Prices rose.', undefined, { timeout: 4000 })).toBeInTheDocument();
    expect(screen.getByText('Normal', { selector: '.mode-badge span:last-child' })).toBeInTheDocument();
    expect(await screen.findByRole('link', { name: /Source A/ })).toHaveAttribute('href', 'https://ex.test/a');
    expect(FakeEventSource.instances[0]?.closed).toBe(true);
    await waitFor(() => expect(screen.getByRole('combobox', { name: 'Your question' })).not.toBeDisabled());
  });

  it('shows a failed run as a failure with Retry, not a blank answer', async () => {
    mockApi(({ method, path }) => {
      if (method === 'GET' && path === '/chats/c1')
        return {
          json: {
            chat,
            messages: [{ id: 'm1', chat_id: 'c1', role: 'user', content: 'Q', run_id: 'r2', mode: 'agentic', created_at: iso() }],
          },
        };
      if (method === 'GET' && path === '/bubbles') return { json: bubbles };
      if (method === 'GET' && path === '/sources') return { json: [] };
      if (method === 'GET' && path === '/settings/provider') return { json: provider };
      if (method === 'GET' && path === '/runs/r2')
        return { json: { id: 'r2', chat_id: 'c1', mode: 'agentic', status: 'failed', answer: null, error: 'Provider rate limit reached', started_at: iso(), finished_at: iso(3) } };
      if (method === 'GET' && path === '/runs/r2/steps') return { json: [] };
      return { status: 500 };
    });
    renderChat();
    expect(await screen.findByText('Provider rate limit reached')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Retry' })).toBeInTheDocument();
    expect(screen.getByRole('alert')).toHaveTextContent('Could not finish');
  });

  it('reports a cancelled run as Stopped and keeps the trace link', async () => {
    mockApi(({ method, path }) => {
      if (method === 'GET' && path === '/chats/c1')
        return {
          json: {
            chat,
            messages: [{ id: 'm1', chat_id: 'c1', role: 'user', content: 'Q', run_id: 'r3', mode: 'normal', created_at: iso() }],
          },
        };
      if (method === 'GET' && path === '/bubbles') return { json: bubbles };
      if (method === 'GET' && path === '/sources') return { json: [] };
      if (method === 'GET' && path === '/settings/provider') return { json: provider };
      if (method === 'GET' && path === '/runs/r3')
        return { json: { id: 'r3', chat_id: 'c1', mode: 'normal', status: 'cancelled', answer: null, error: null, started_at: iso(), finished_at: iso(2) } };
      if (method === 'GET' && path === '/runs/r3/steps') return { json: [] };
      return { status: 500 };
    });
    renderChat();
    expect(await screen.findByText('Stopped')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'View trace' })).toHaveAttribute('href', '/app/trace/r3');
  });

  it('shows the 404 page for an unknown chat with a link back to Chat', async () => {
    mockApi(({ method, path }) => {
      if (method === 'GET' && path === '/chats/missing') return { status: 404, json: { detail: 'unknown chat' } };
      if (method === 'GET' && path === '/bubbles') return { json: bubbles };
      if (method === 'GET' && path === '/sources') return { json: [] };
      if (method === 'GET' && path === '/settings/provider') return { json: provider };
      return { status: 500 };
    });
    renderChat('/app/chat/missing');
    const heading = await screen.findByRole('heading', { name: 'Chat not found' });
    await waitFor(() => expect(heading).toHaveFocus());
    expect(screen.getByRole('link', { name: 'Back to chat' })).toHaveAttribute('href', '/app');
  });
});
