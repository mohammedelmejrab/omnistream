import { useEffect } from 'react';

const APP_NAME = 'OmniStream';

/** Sets the page title for a route (WCAG 2.4.2). */
export function useDocumentTitle(title: string | null): void {
  useEffect(() => {
    document.title = title ? `${title} · ${APP_NAME}` : APP_NAME;
  }, [title]);
}
