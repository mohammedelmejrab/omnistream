import { useCallback, useState, type ReactElement } from 'react';
import { NavLink, Link } from 'react-router';
import { listChats } from '@/api/chats';
import { useResource } from '@/hooks/useResource';
import { useChatsChanged } from '@/hooks/chatsChanged';
import { useMediaQuery } from '@/hooks/useMediaQuery';
import { useRefetchOnFocus } from '@/hooks/useRefetchOnFocus';
import { MenuIcon } from '@/components/Icons';

const NARROW = '(max-width: 1024px)';

/**
 * Recent rail (spec 11.2). Collapses at 1024px and below (spec 11.1, decision 31); the toggle
 * is the only control shown while collapsed.
 */
export function Rail({ activeChatId }: { activeChatId: string }): ReactElement {
  const narrow = useMediaQuery(NARROW);
  const [override, setOverride] = useState<boolean | null>(null);
  const collapsed = override ?? narrow;
  const chats = useResource((signal) => listChats(signal), []);
  const reload = chats.reload;
  useChatsChanged(useCallback(() => reload(), [reload]));
  useRefetchOnFocus(reload);

  return (
    <nav aria-label="Recent chats" className={collapsed ? 'rail rail-collapsed' : 'rail'}>
      <button
        type="button"
        className="btn btn-ghost rail-toggle"
        aria-expanded={!collapsed}
        aria-controls="rail-body"
        onClick={() => setOverride(!collapsed)}
      >
        <MenuIcon size={18} />
        <span className={collapsed ? 'sr-only' : undefined}>{collapsed ? 'Show recent chats' : 'Hide recent chats'}</span>
      </button>
      <div id="rail-body" hidden={collapsed}>
        <h2 className="rail-heading">Recent</h2>
        {chats.error && <p className="muted">Could not load chats.</p>}
        <ul className="rail-list">
          {(chats.data ?? []).slice(0, 30).map((c) => (
            <li key={c.id}>
              <NavLink
                to={`/app/chat/${c.id}`}
                className="rail-link"
                aria-current={c.id === activeChatId ? 'page' : undefined}
              >
                {c.title || 'Untitled chat'}
              </NavLink>
            </li>
          ))}
        </ul>
        <Link to="/app/chats" className="rail-link rail-seeall">
          See all
        </Link>
      </div>
    </nav>
  );
}
