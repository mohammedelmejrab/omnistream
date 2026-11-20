import type { ReactElement } from 'react';
import type { Source } from '@/api/types';
import { StatusChip } from '@/components/StatusChip';
import { formatWhen, type SourceStatus } from './sourceStatus';

interface SourceRowProps {
  source: Source;
  status: SourceStatus;
  name: string;
  busy: boolean;
  highlighted: boolean;
  onToggle: (source: Source) => void;
  onEdit: (source: Source) => void;
  onDelete: (source: Source) => void;
}

/** One source row (r-md card, spec 11). Status is an icon and a word. */
export function SourceRow(props: SourceRowProps): ReactElement {
  const { source, status, name, busy, highlighted, onToggle, onEdit, onDelete } = props;
  const isDocument = source.type === 'document';
  return (
    <li id={`source-${source.id}`} className={highlighted ? 'source-row source-row-highlight' : 'source-row'}>
      <div className="source-main">
        <div className="source-title">
          <span className="source-type">{typeWord(source)}</span>
          <span className="source-name" title={name}>
            {name}
          </span>
        </div>
        <div className="source-meta">
          <StatusChip tone={status.tone} label={status.label} />
          {!isDocument && <span className="muted">Last checked: {formatWhen(source.last_polled_at)}</span>}
        </div>
        {source.status === 'error' && source.last_error && (
          <p className="source-error" role="status">
            {source.last_error}
          </p>
        )}
      </div>
      <div className="source-actions">
        {!isDocument && (
          <button
            type="button"
            role="switch"
            aria-checked={source.enabled}
            className="switch"
            disabled={busy}
            onClick={() => onToggle(source)}
          >
            <span aria-hidden="true" className="switch-knob" />
            <span>{source.enabled ? 'Enabled' : 'Paused'}</span>
            <span className="sr-only">for {name}</span>
          </button>
        )}
        {!isDocument && (
          <button type="button" className="btn btn-pill" disabled={busy} onClick={() => onEdit(source)}>
            Edit<span className="sr-only"> {name}</span>
          </button>
        )}
        <button
          type="button"
          className="btn btn-pill btn-danger"
          disabled={busy}
          onClick={() => onDelete(source)}
        >
          Delete<span className="sr-only"> {name}</span>
        </button>
      </div>
    </li>
  );
}

function typeWord(source: Source): string {
  switch (source.type) {
    case 'rss':
      return 'Feed';
    case 'api':
      return 'API';
    case 'document':
      return 'Document';
    default:
      return 'Source';
  }
}
