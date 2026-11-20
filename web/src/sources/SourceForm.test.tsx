import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router';
import { describe, expect, it } from 'vitest';
import { mockApi, iso } from '@/test/api-mock';
import { SourceForm } from './SourceForm';
import type { Source } from '@/api/types';

const existing: Source = {
  id: 'src-1',
  type: 'rss',
  url: 'https://example.com/feed',
  credibility: 0.5,
  poll_interval: 900,
  bubble_ids: ['b1'],
  api_mapping: null,
  max_items_per_hour: 30,
  store_full_text: true,
  enabled: true,
  last_polled_at: null,
  status: 'ok',
  last_error: null,
};
const bubbles = [{ id: 'b1', name: 'Energy', description: '', half_life_days: 30, created_at: iso(), updated_at: iso() }];

function renderForm() {
  return render(
    <MemoryRouter>
      <SourceForm kind="rss" bubbles={bubbles} existing={[existing]} onSaved={() => undefined} onCancel={() => undefined} />
    </MemoryRouter>,
  );
}

describe('SourceForm validation', () => {
  it('rejects an invalid URL inline before any request is sent', async () => {
    const user = userEvent.setup();
    const mock = mockApi(() => ({ status: 500 }));
    renderForm();
    await user.type(screen.getByLabelText('Feed URL'), 'not a url');
    await user.click(screen.getByLabelText('Energy'));
    await user.click(screen.getByRole('button', { name: 'Add source' }));
    expect(screen.getByText(/starts with http:\/\/ or https:\/\//)).toBeInTheDocument();
    expect(mock.calls).toHaveLength(0);
  });

  it('says "Already added" with a link to the existing source for a duplicate URL', async () => {
    const user = userEvent.setup();
    const mock = mockApi(({ method, path }) => (method === 'GET' && path === '/sources' ? { json: [existing] } : { status: 500 }));
    renderForm();
    await user.type(screen.getByLabelText('Feed URL'), 'https://Example.com/feed/');
    await user.click(screen.getByLabelText('Energy'));
    await user.click(screen.getByRole('button', { name: 'Add source' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Already added.');
    expect(screen.getByRole('link', { name: 'View the existing source' })).toHaveAttribute('href', '#source-src-1');
    // The check reads the server's list at submit time, and no source is created.
    expect(mock.calls.map((c) => `${c.method} ${c.path}`)).toEqual(['GET /sources']);
  });

  it('checks the server list at submit time, so a source added elsewhere is still caught', async () => {
    const user = userEvent.setup();
    const mock = mockApi(({ method, path }) => (method === 'GET' && path === '/sources' ? { json: [existing] } : { status: 500 }));
    // The form was opened before src-1 existed: the prop list is stale.
    render(
      <MemoryRouter>
        <SourceForm kind="rss" bubbles={bubbles} existing={[]} onSaved={() => undefined} onCancel={() => undefined} />
      </MemoryRouter>,
    );
    await user.type(screen.getByLabelText('Feed URL'), 'https://example.com/feed');
    await user.click(screen.getByLabelText('Energy'));
    await user.click(screen.getByRole('button', { name: 'Add source' }));
    expect(await screen.findByText('Already added.')).toBeInTheDocument();
    expect(mock.calls.some((c) => c.method === 'POST')).toBe(false);
  });

  it('handles a server 409 for a duplicate by linking to the existing source', async () => {
    const user = userEvent.setup();
    let listed = 0;
    mockApi(({ method, path }) => {
      if (method === 'GET' && path === '/sources') {
        listed += 1;
        // First check (before submit) sees nothing; the list after the 409 has the source.
        return { json: listed === 1 ? [] : [existing] };
      }
      if (method === 'POST' && path === '/sources') return { status: 409, json: { detail: 'Source already exists' } };
      return { status: 500 };
    });
    render(
      <MemoryRouter>
        <SourceForm kind="rss" bubbles={bubbles} existing={[]} onSaved={() => undefined} onCancel={() => undefined} />
      </MemoryRouter>,
    );
    await user.type(screen.getByLabelText('Feed URL'), 'https://example.com/feed');
    await user.click(screen.getByLabelText('Energy'));
    await user.click(screen.getByRole('button', { name: 'Add source' }));
    expect(await screen.findByText('Already added.')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'View the existing source' })).toHaveAttribute('href', '#source-src-1');
    expect(listed).toBe(2);
  });

  it('shows the server message for a 409 it cannot match to a listed source', async () => {
    const user = userEvent.setup();
    mockApi(({ method, path }) => {
      if (method === 'GET' && path === '/sources') return { json: [] };
      if (method === 'POST' && path === '/sources') return { status: 409, json: { detail: 'Source already exists' } };
      return { status: 500 };
    });
    renderForm();
    await user.type(screen.getByLabelText('Feed URL'), 'https://other.example/feed');
    await user.click(screen.getByLabelText('Energy'));
    await user.click(screen.getByRole('button', { name: 'Add source' }));
    expect(await screen.findByText('Source already exists')).toBeInTheDocument();
    expect(screen.queryByText('Already added.')).not.toBeInTheDocument();
  });

  it('requires at least one bubble', async () => {
    const user = userEvent.setup();
    renderForm();
    await user.type(screen.getByLabelText('Feed URL'), 'https://other.example/feed');
    await user.click(screen.getByRole('button', { name: 'Add source' }));
    expect(screen.getByText('Choose at least one bubble for this source.')).toBeInTheDocument();
  });
});
