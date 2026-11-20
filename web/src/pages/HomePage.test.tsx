import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { RouterProvider, createMemoryRouter } from 'react-router';
import { describe, expect, it } from 'vitest';
import { mockApi, iso } from '@/test/api-mock';
import { HomePage, SUGGESTIONS } from './HomePage';

const provider = { key_set: true, key_hint: 'a7f2', key_source: 'ui', base_url: 'https://x.test/v1', model: 'm' };
const bubbles = [{ id: 'b1', name: 'Energy', description: '', half_life_days: 30, created_at: iso(), updated_at: iso() }];

function renderHome() {
  const router = createMemoryRouter([{ path: '/app', element: <HomePage /> }], { initialEntries: ['/app'] });
  return render(<RouterProvider router={router} />);
}

function baseMock(chats: unknown[] = []) {
  return mockApi(({ method, path }) => {
    if (method === 'GET' && path === '/settings/provider') return { json: provider };
    if (method === 'GET' && path === '/bubbles') return { json: bubbles };
    if (method === 'GET' && path === '/sources') return { json: [] };
    if (method === 'GET' && path === '/chats') return { json: chats };
    return { status: 500 };
  });
}

describe('HomePage', () => {
  it('opens on "Where should we start?" with three suggestions and no Recent row when there are no chats', async () => {
    baseMock([]);
    renderHome();
    expect(screen.getByRole('heading', { level: 1, name: 'Where should we start?' })).toBeInTheDocument();
    expect(screen.getAllByRole('button', { name: /^(Summarise|What is new|Compare)/ })).toHaveLength(SUGGESTIONS.length);
    await waitFor(() => expect(screen.queryByText('Recent:')).not.toBeInTheDocument());
  });

  it('shows up to three Recent chips with See all when chats exist', async () => {
    const chat = (id: string, title: string) => ({ id, title, mode: 'normal', created_at: iso(), updated_at: iso() });
    baseMock([chat('c1', 'EU energy'), chat('c2', 'Tax'), chat('c3', 'Health'), chat('c4', 'Extra')]);
    renderHome();
    expect(await screen.findByRole('link', { name: 'EU energy' })).toHaveAttribute('href', '/app/chat/c1');
    expect(screen.queryByRole('link', { name: 'Extra' })).not.toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'See all' })).toHaveAttribute('href', '/app/chats');
  });

  it('puts the suggestion into the input without sending it', async () => {
    const user = userEvent.setup();
    const mock = baseMock([]);
    renderHome();
    await user.click(screen.getByRole('button', { name: SUGGESTIONS[1] ?? '' }));
    expect(screen.getByRole('combobox', { name: 'Your question' })).toHaveValue(SUGGESTIONS[1]);
    expect(mock.calls.some((c) => c.method === 'POST')).toBe(false);
  });

  it('says a key is missing and blocks sending, with a link to Settings', async () => {
    mockApi(({ method, path }) => {
      if (method === 'GET' && path === '/settings/provider')
        return { json: { ...provider, key_set: false, key_hint: null, key_source: null } };
      if (method === 'GET' && path === '/bubbles') return { json: bubbles };
      if (method === 'GET' && path === '/sources') return { json: [] };
      if (method === 'GET' && path === '/chats') return { json: [] };
      return { status: 500 };
    });
    renderHome();
    expect(await screen.findByText(/No provider key is set/)).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Add a key in Settings' })).toHaveAttribute('href', '/app/settings');
  });
});
