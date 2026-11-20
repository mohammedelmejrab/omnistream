import type { ReactElement } from 'react';
import { Link } from 'react-router';
import { Sheet } from '@/layout/Sheet';
import { SourcesPanel } from './SourcesPanel';

/** The "+" menu: the Sources panel in a side sheet (spec 6 and 8). */
export function SourcesSheet({ open, onClose }: { open: boolean; onClose: () => void }): ReactElement | null {
  return (
    <Sheet open={open} onClose={onClose} titleId="sources-sheet-title" title="Sources">
      <p className="muted">
        Add feeds, APIs and documents to your bubbles. Ingestion runs in the background. <Link to="/app/sources" onClick={onClose}>Open the full sources page</Link>.
      </p>
      <SourcesPanel />
    </Sheet>
  );
}
