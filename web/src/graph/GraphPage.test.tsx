import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { getGraph } from '../api/graph';
import type { GraphResponse } from '../api/types';
import { GraphPage } from './GraphPage';

vi.mock('../api/graph', () => ({ getGraph: vi.fn() }));
vi.mock('./GraphCanvas', () => import('./testing/GraphCanvasStub'));

const getGraphMock = vi.mocked(getGraph);

const PAGE_ONE: GraphResponse = {
  nodes: [
    { id: 'g1', label: 'Gas prices', bubble: 'Energy', kind: 'entity' },
    { id: 'g2', label: 'Oil output', bubble: 'Energy', kind: 'entity' },
  ],
  edges: [{ id: 'ge1', source: 'g1', target: 'g2', label: 'related' }],
  total: 3,
};

const PAGE_TWO: GraphResponse = {
  nodes: [{ id: 'g3', label: 'Vote count', bubble: 'Policy', kind: 'chunk' }],
  edges: [],
  total: 3,
};

function renderPage() {
  return render(
    <MemoryRouter>
      <GraphPage />
    </MemoryRouter>,
  );
}

beforeEach(() => {
  getGraphMock.mockReset();
});

describe('GraphPage', () => {
  it('loads the first page, shows the count and counts per bubble', async () => {
    getGraphMock.mockResolvedValueOnce(PAGE_ONE);
    renderPage();
    expect(await screen.findByText('Showing 2 of 3 nodes')).toBeInTheDocument();
    expect(getGraphMock).toHaveBeenCalledWith(
      { bubble: '', limit: 300, offset: 0 },
      expect.any(AbortSignal),
    );
    expect(screen.getByText('Energy: 2 loaded')).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Graph' })).toBeInTheDocument();
  });

  it('search by name narrows the node list and dims the rest on the canvas', async () => {
    const user = userEvent.setup();
    getGraphMock.mockResolvedValueOnce(PAGE_ONE);
    renderPage();
    await screen.findByText('Showing 2 of 3 nodes');
    await user.type(screen.getByRole('searchbox', { name: 'Search by name' }), 'gas');
    const list = screen.getByRole('listbox', { name: 'Graph nodes' });
    expect(within(list).getAllByRole('option')).toHaveLength(1);
    expect(screen.getByTestId('graph-canvas')).toHaveAttribute('data-dimmed', '1');
  });

  it('a bubble filter asks the API for that bubble only', async () => {
    const user = userEvent.setup();
    getGraphMock.mockResolvedValueOnce(PAGE_ONE);
    renderPage();
    await screen.findByText('Showing 2 of 3 nodes');
    getGraphMock.mockResolvedValueOnce({ nodes: [], edges: [], total: 0 });
    await user.selectOptions(screen.getByRole('combobox', { name: /^Bubble/ }), 'Energy');
    await waitFor(() =>
      expect(getGraphMock).toHaveBeenLastCalledWith(
        { bubble: 'Energy', limit: 300, offset: 0 },
        expect.any(AbortSignal),
      ),
    );
  });

  it('load more fetches the next page from the current offset', async () => {
    const user = userEvent.setup();
    getGraphMock.mockResolvedValueOnce(PAGE_ONE).mockResolvedValueOnce(PAGE_TWO);
    renderPage();
    await screen.findByText('Showing 2 of 3 nodes');
    await user.click(screen.getByRole('button', { name: 'Load more (1 left)' }));
    expect(await screen.findByText('Showing 3 of 3 nodes')).toBeInTheDocument();
    expect(getGraphMock).toHaveBeenLastCalledWith({ bubble: '', limit: 300, offset: 2 });
    expect(screen.queryByRole('button', { name: /Load more/ })).not.toBeInTheDocument();
  });

  it('an empty graph shows an empty state that links to Sources', async () => {
    getGraphMock.mockResolvedValueOnce({ nodes: [], edges: [], total: 0 });
    renderPage();
    expect(await screen.findByRole('heading', { name: 'The graph is empty' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Go to Sources' })).toHaveAttribute('href', '/app/sources');
  });

  it('a failed load shows an alert', async () => {
    getGraphMock.mockRejectedValueOnce(new Error('down'));
    renderPage();
    expect(await screen.findByRole('alert')).toHaveTextContent('The graph could not be loaded');
  });

  it('selecting a node opens a read-only detail panel that Esc closes', async () => {
    const user = userEvent.setup();
    getGraphMock.mockResolvedValueOnce(PAGE_ONE);
    renderPage();
    await screen.findByText('Showing 2 of 3 nodes');
    const option = within(screen.getByRole('listbox', { name: 'Graph nodes' })).getByText('Gas prices');
    await user.click(option);
    const panel = await screen.findByRole('complementary', { name: 'Gas prices' });
    expect(within(panel).getByText('Node kind: entity')).toBeInTheDocument();
    await user.keyboard('{Escape}');
    expect(screen.queryByRole('complementary', { name: 'Gas prices' })).not.toBeInTheDocument();
  });
});
