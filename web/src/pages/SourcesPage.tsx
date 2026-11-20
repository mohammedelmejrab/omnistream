import type { ReactElement } from 'react';
import { useDocumentTitle } from '@/hooks/useDocumentTitle';
import { SourcesPanel } from '@/sources/SourcesPanel';

/** /app/sources: the same menu as the "+" sheet, as a full page (spec 5). */
export function SourcesPage(): ReactElement {
  useDocumentTitle('Sources');
  return (
    <div className="page">
      <h1 tabIndex={-1}>Sources</h1>
      <p className="muted">Feeds, APIs and documents, grouped by the bubble they feed.</p>
      <SourcesPanel />
    </div>
  );
}
