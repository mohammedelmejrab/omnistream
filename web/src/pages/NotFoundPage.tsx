import { useEffect, useRef, type ReactElement } from 'react';
import { Link } from 'react-router';
import { useDocumentTitle } from '@/hooks/useDocumentTitle';

/** 404 for an unknown chat or run, or an unknown route (spec 13). */
export function NotFoundPage({ what = 'page' }: { what?: 'page' | 'chat' | 'run' }): ReactElement {
  const headingRef = useRef<HTMLHeadingElement>(null);
  const title = what === 'chat' ? 'Chat not found' : what === 'run' ? 'Run not found' : 'Page not found';
  useDocumentTitle(title);
  useEffect(() => {
    headingRef.current?.focus();
  }, []);
  return (
    <div className="status-page">
      <h1 tabIndex={-1} ref={headingRef}>
        {title}
      </h1>
      <p className="muted">
        {what === 'chat'
          ? 'This chat does not exist. It may have been deleted.'
          : 'The address is not known to OmniStream.'}
      </p>
      <p>
        <Link to="/app" className="btn btn-primary btn-pill">
          Back to chat
        </Link>
      </p>
    </div>
  );
}
