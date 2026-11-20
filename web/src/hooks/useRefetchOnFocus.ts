import { useEffect, useRef } from 'react';

/**
 * Calls `refetch` when the window regains focus or the tab becomes visible.
 * Used so a second tab on the same chat picks up new messages (spec 10.4).
 */
export function useRefetchOnFocus(refetch: () => void, enabled = true): void {
  const ref = useRef(refetch);
  ref.current = refetch;
  useEffect(() => {
    if (!enabled) return;
    const onFocus = (): void => ref.current();
    const onVisible = (): void => {
      if (document.visibilityState === 'visible') ref.current();
    };
    window.addEventListener('focus', onFocus);
    document.addEventListener('visibilitychange', onVisible);
    return () => {
      window.removeEventListener('focus', onFocus);
      document.removeEventListener('visibilitychange', onVisible);
    };
  }, [enabled]);
}
