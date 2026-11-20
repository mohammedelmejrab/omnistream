import { lazy, Suspense, type ReactElement } from 'react';
import { createBrowserRouter, Navigate } from 'react-router';
import { AppShell } from '@/layout/AppShell';
import { ChatPage } from '@/pages/ChatPage';
import { ChatsPage } from '@/pages/ChatsPage';
import { HomePage } from '@/pages/HomePage';
import { NotFoundPage } from '@/pages/NotFoundPage';
import { ServerDownPage } from '@/pages/ServerDownPage';
import { useDocumentTitle } from '@/hooks/useDocumentTitle';
import { SettingsPage } from '@/pages/SettingsPage';
import { SourcesPage } from '@/pages/SourcesPage';

// The trace and graph viewers pull in Cytoscape, so they load on demand.
const TracePage = lazy(() => import('@/trace').then((m) => ({ default: m.TracePage })));
const GraphPage = lazy(() => import('@/graph').then((m) => ({ default: m.GraphPage })));

/** Lazy route. The page title is set here because the lazy pages do not set it themselves. */
function Lazy({ title, children }: { title: string; children: ReactElement }): ReactElement {
  useDocumentTitle(title);
  return <Suspense fallback={<p className="muted" role="status">Loading…</p>}>{children}</Suspense>;
}

// Route map from spec section 5. Every page sets its own title and moves
// focus to its h1 on route change (AppShell).
export const router = createBrowserRouter([
  { path: '/', element: <Navigate to="/app" replace /> },
  {
    path: '/app',
    element: <AppShell />,
    errorElement: <ServerDownPage />,
    children: [
      { index: true, element: <HomePage /> },
      { path: 'chat/:chatId', element: <ChatPage /> },
      { path: 'chats', element: <ChatsPage /> },
      { path: 'sources', element: <SourcesPage /> },
      { path: 'graph', element: <Lazy title="Graph"><GraphPage /></Lazy> },
      { path: 'trace/:runId', element: <Lazy title="Trace"><TracePage /></Lazy> },
      { path: 'settings', element: <SettingsPage /> },
      { path: '*', element: <NotFoundPage /> },
    ],
  },
  { path: '*', element: <NotFoundPage /> },
]);
