import { act, render, screen, waitFor } from '@testing-library/react';
import { RouterProvider, createMemoryRouter } from 'react-router';
import { describe, expect, it } from 'vitest';
import { AppShell } from './AppShell';
import { useDocumentTitle } from '@/hooks/useDocumentTitle';

function Page({ name, title }: { name: string; title: string }) {
  useDocumentTitle(title);
  return <h1 tabIndex={-1}>{name} heading</h1>;
}

function makeRouter(path: string) {
  return createMemoryRouter(
    [
      {
        path: '/app',
        element: <AppShell />,
        children: [
          { index: true, element: <Page name="Home" title="Ask" /> },
          { path: 'sources', element: <Page name="Sources" title="Sources" /> },
          { path: 'settings', element: <Page name="Settings" title="Settings" /> },
        ],
      },
    ],
    { initialEntries: [path] },
  );
}

describe('AppShell', () => {
  it('offers a skip link to the main content as the first control', () => {
    render(<RouterProvider router={makeRouter('/app')} />);
    const skip = screen.getByRole('link', { name: 'Skip to main content' });
    expect(skip).toHaveAttribute('href', '#main');
    expect(screen.getByRole('main')).toHaveAttribute('id', 'main');
  });

  it('sets the page title for each route', () => {
    render(<RouterProvider router={makeRouter('/app/sources')} />);
    expect(document.title).toBe('Sources · OmniStream');
  });

  it('moves focus to the main heading on route change, not on first load', async () => {
    const router = makeRouter('/app');
    render(<RouterProvider router={router} />);
    expect(screen.getByRole('heading', { name: 'Home heading' })).not.toHaveFocus();
    await act(async () => {
      await router.navigate('/app/settings');
    });
    await waitFor(() => expect(screen.getByRole('heading', { name: 'Settings heading' })).toHaveFocus());
    expect(document.title).toBe('Settings · OmniStream');
  });

  it('marks the current section in the primary navigation', () => {
    render(<RouterProvider router={makeRouter('/app/settings')} />);
    const nav = screen.getByRole('navigation', { name: 'Primary' });
    expect(nav.querySelector('[aria-current="page"]')).toHaveTextContent('Settings');
  });
});
