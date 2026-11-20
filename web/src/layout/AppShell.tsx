import { useEffect, useRef, type ReactElement } from 'react';
import { Link, NavLink, Outlet, useLocation, useMatch } from 'react-router';
import { Rail } from './Rail';

/**
 * Shared frame for every route: skip link, primary navigation, the Recent
 * rail on chat pages only (spec 6 and 11.2), and focus on the main heading
 * after a route change (spec 5, WCAG 2.4.2).
 */
export function AppShell(): ReactElement {
  const location = useLocation();
  const chatMatch = useMatch('/app/chat/:chatId');
  const mainRef = useRef<HTMLElement>(null);
  const seenFirst = useRef(false);

  useEffect(() => {
    if (!seenFirst.current) {
      seenFirst.current = true;
      return;
    }
    const heading = mainRef.current?.querySelector<HTMLElement>('h1');
    heading?.focus({ preventScroll: true });
  }, [location.pathname]);

  return (
    <div className="app">
      <a href="#main" className="skip-link">
        Skip to main content
      </a>
      <header className="app-header">
        <Link to="/app" className="brand">
          OmniStream
        </Link>
        <nav aria-label="Primary" className="primary-nav">
          <NavLink to="/app/chats" className="nav-link">
            Chats
          </NavLink>
          <NavLink to="/app/sources" className="nav-link">
            Sources
          </NavLink>
          <NavLink to="/app/graph" className="nav-link">
            Graph
          </NavLink>
          <NavLink to="/app/settings" className="nav-link">
            Settings
          </NavLink>
        </nav>
      </header>
      <div className="app-body">
        {chatMatch && <Rail activeChatId={chatMatch.params.chatId ?? ''} />}
        <main id="main" ref={mainRef} tabIndex={-1} className="main">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
