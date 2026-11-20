import { useEffect, useRef, type ReactElement } from 'react';
import { Link, isRouteErrorResponse, useRouteError } from 'react-router';
import { useDocumentTitle } from '@/hooks/useDocumentTitle';
import { NotFoundPage } from './NotFoundPage';

/** Router-level error boundary: a 404 response, or anything else (server down). */
export function ServerDownPage(): ReactElement {
  const error = useRouteError();
  const headingRef = useRef<HTMLHeadingElement>(null);
  useDocumentTitle('Something went wrong');
  useEffect(() => {
    headingRef.current?.focus();
  }, []);
  if (isRouteErrorResponse(error) && error.status === 404) {
    return <NotFoundPage />;
  }
  return (
    <div className="status-page">
      <h1 tabIndex={-1} ref={headingRef}>
        OmniStream could not load this page
      </h1>
      <p className="muted">
        The server may be down, or the page failed to start. Check that OmniStream is running, then try again.
      </p>
      <p>
        <Link to="/app" className="btn btn-primary btn-pill">
          Back to chat
        </Link>
      </p>
    </div>
  );
}
