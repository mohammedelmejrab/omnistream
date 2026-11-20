import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { RouterProvider, createMemoryRouter } from 'react-router';
import { describe, expect, it } from 'vitest';
import { mockApi } from '@/test/api-mock';
import { SettingsPage } from './SettingsPage';

const provider = {
  key_set: true,
  key_hint: 'a7f2',
  key_source: 'ui',
  base_url: 'https://api.example.test/v1',
  model: 'some-model',
};

function renderPage() {
  const router = createMemoryRouter([{ path: '/app/settings', element: <SettingsPage /> }], {
    initialEntries: ['/app/settings'],
  });
  return render(<RouterProvider router={router} />);
}

describe('SettingsPage', () => {
  it('shows only a masked key, read as "key ending a7f2", and the active source', async () => {
    mockApi(({ method, path }) => {
      if (method === 'GET' && path === '/settings/provider') return { json: provider };
      return { status: 500 };
    });
    const { container } = renderPage();
    expect(await screen.findByText('sk-••••a7f2', { selector: '[aria-hidden="true"]' })).toBeInTheDocument();
    expect(screen.getByText('key ending a7f2')).toBeInTheDocument();
    expect(screen.getByText('Saved in OmniStream')).toBeInTheDocument();
    // No input is pre-filled with a key, and no key-shaped text is rendered.
    expect(container.querySelector('input[type="password"]')).toBeNull();
    expect(container.textContent ?? '').not.toMatch(/sk-[A-Za-z0-9]{8,}/);
  });

  it('masks an environment key that has no hint without claiming an ending', async () => {
    mockApi(({ method, path }) => {
      if (method === 'GET' && path === '/settings/provider')
        return { json: { ...provider, key_hint: null, key_source: 'env' } };
      return { status: 500 };
    });
    renderPage();
    expect(await screen.findByText('sk-••••••••', { selector: '[aria-hidden="true"]' })).toBeInTheDocument();
    expect(screen.getByText('API key is set')).toBeInTheDocument();
    expect(screen.queryByText(/key ending/)).toBeNull();
  });

  it('opens the replacement input with focus on it, and Cancel returns focus to Replace key', async () => {
    const user = userEvent.setup();
    mockApi(({ method, path }) => {
      if (method === 'GET' && path === '/settings/provider') return { json: provider };
      return { status: 500 };
    });
    renderPage();
    const replace = await screen.findByRole('button', { name: 'Replace key' });
    await user.click(replace);
    await waitFor(() => expect(screen.getByLabelText('New API key')).toHaveFocus());
    await user.click(screen.getByRole('button', { name: 'Cancel' }));
    expect(screen.getByRole('button', { name: 'Replace key' })).toHaveFocus();
  });

  it('saves the endpoint without sending a key when none was typed', async () => {
    const user = userEvent.setup();
    const mock = mockApi(({ method, path }) => {
      if (method === 'GET' && path === '/settings/provider') return { json: provider };
      if (method === 'PUT') return { json: provider };
      return { status: 500 };
    });
    renderPage();
    await user.click(await screen.findByRole('button', { name: 'Save' }));
    await screen.findByText('Settings saved.');
    const put = mock.calls.find((c) => c.method === 'PUT');
    expect(put?.body).toEqual({ base_url: provider.base_url, model: provider.model });
  });

  it('rejects a base URL that is not http or https before saving', async () => {
    const user = userEvent.setup();
    const mock = mockApi(({ method, path }) => {
      if (method === 'GET' && path === '/settings/provider') return { json: provider };
      return { status: 500 };
    });
    renderPage();
    const base = await screen.findByLabelText('Base URL');
    await user.clear(base);
    await user.type(base, 'ftp://nope');
    await user.click(screen.getByRole('button', { name: 'Save' }));
    expect(screen.getByText(/starts with http:\/\/ or https:\/\//)).toBeInTheDocument();
    expect(mock.calls.some((c) => c.method === 'PUT')).toBe(false);
  });
});
