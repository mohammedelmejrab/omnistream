import { useEffect, useId, useRef } from 'react';
import { relevanceBand, STEP_STATUS_WORD } from '../trace/model';
import type { DetailModel } from './detail';

// 360px detail panel (spec 10.3). Focus moves here on open; Esc closes it and the
// caller returns focus to whatever opened it.

export interface DetailPanelProps {
  detail: DetailModel;
  onClose(): void;
  onToggleGroup?(bubble: string): void;
  onJumpToCitation?(itemId: string): void;
}

const STATUS_ICON: Record<string, string> = { ok: '✓', running: '…', error: '✕', cancelled: '■' };

export function DetailPanel({ detail, onClose, onToggleGroup, onJumpToCitation }: DetailPanelProps) {
  const ref = useRef<HTMLElement | null>(null);
  const titleId = useId();

  useEffect(() => {
    ref.current?.focus();
  }, [detail.id]);

  return (
    <aside
      ref={ref}
      tabIndex={-1}
      className="detail-panel"
      aria-labelledby={titleId}
      onKeyDown={(e) => {
        if (e.key === 'Escape') {
          e.stopPropagation();
          onClose();
        }
      }}
    >
      <header className="detail-panel-header">
        <div>
          <p className="detail-kind">{detail.kindNote}</p>
          <h2 id={titleId} className="detail-title">
            {detail.title}
          </h2>
        </div>
        <button type="button" className="text-button" onClick={onClose}>
          Close
        </button>
      </header>

      {detail.status && (
        <p className="detail-status">
          <span aria-hidden="true">{STATUS_ICON[detail.status] ?? '•'}</span>{' '}
          {STEP_STATUS_WORD[detail.status]}
        </p>
      )}

      {detail.relevance !== null && (
        <p className="detail-relevance">
          Relevance: {relevanceBand(detail.relevance)} ({detail.relevance.toFixed(2)})
        </p>
      )}

      {detail.error && (
        <p className="detail-error" role="alert">
          {detail.error}
        </p>
      )}

      {detail.rows.length > 0 && (
        <dl className="detail-rows">
          {detail.rows.map((row) => (
            <div key={row.label} className="detail-row">
              <dt>{row.label}</dt>
              <dd>{row.value}</dd>
            </div>
          ))}
        </dl>
      )}

      {detail.sourceText && (
        <section aria-label="Source text">
          <h3>Source text</h3>
          <blockquote className="detail-source">{detail.sourceText}</blockquote>
        </section>
      )}

      {detail.group && onToggleGroup && (
        <button
          type="button"
          className="pill-button"
          aria-expanded={detail.group.expanded}
          onClick={() => onToggleGroup(detail.group!.bubble)}
        >
          {detail.group.expanded ? 'Collapse entities and chunks' : 'Expand entities and chunks'}
        </button>
      )}

      {detail.citations.length > 0 && (
        <section aria-label="Cited items">
          <h3>Cited items</h3>
          <ul className="citation-list">
            {detail.citations.map((c) => (
              <li key={c.item_id} className="citation-item">
                <span className="citation-title">{c.title || c.item_id}</span>
                {c.url && (
                  <a href={c.url} target="_blank" rel="noopener noreferrer">
                    Open source (opens in a new tab)
                  </a>
                )}
                {onJumpToCitation && (
                  <button
                    type="button"
                    className="pill-button"
                    onClick={() => onJumpToCitation(c.item_id)}
                  >
                    Show in graph
                  </button>
                )}
              </li>
            ))}
          </ul>
        </section>
      )}
    </aside>
  );
}
