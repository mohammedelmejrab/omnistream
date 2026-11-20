import { relevanceBand, STAGE_STATUS_WORD, type SimpleView as SimpleViewModel, type Stage, type StageStatus } from './model';
import { formatDuration } from './format';
import { Timeline } from './Timeline';

export { formatDuration };

// Simple four-stage view (spec 10.2). Status is an icon plus a word, never colour alone.

const STAGE_ICON: Record<StageStatus, string> = {
  done: '✓',
  working: '…',
  failed: '✕',
  'no-evidence': '∅',
  pending: '○',
};

export interface SimpleViewProps {
  view: SimpleViewModel;
  /** Index of the stage replay is on, or -1. */
  currentStage: number;
  onSelectStage(index: number): void;
}

export function SimpleView({ view, currentStage, onSelectStage }: SimpleViewProps) {
  const timelineItems = view.stages.map((s) => ({
    id: s.key,
    label: s.title,
    durationMs: s.durationMs,
    statusWord: STAGE_STATUS_WORD[s.status],
    statusClass: `stage-${s.status}`,
  }));

  return (
    <section className="simple-view" aria-label="Simple trace">
      <ol className="stage-list" aria-label="Trace stages">
        {view.stages.map((stage, i) => (
          <StageItem key={stage.key} stage={stage} number={i + 1} current={i === currentStage} />
        ))}
      </ol>
      <Timeline
        variant="stages"
        label="Duration of each stage"
        items={timelineItems}
        currentIndex={currentStage}
        onSelect={onSelectStage}
      />
      {/* The strip has no text of its own; this legend says which bar is which stage, its status and how long it took. */}
      <ol className="stage-legend" aria-label="Legend: duration of each stage">
        {view.stages.map((stage, i) => (
          <li key={stage.key} className={i === currentStage ? 'legend-item legend-item-current' : 'legend-item'}>
            <span className={`legend-swatch stage-${stage.status}`} aria-hidden="true" />
            <span className="legend-number">{i + 1}</span>
            <span className="legend-title">{stage.title}</span>
            <span className="legend-time">
              {stage.durationMs === null ? 'duration unknown' : formatDuration(stage.durationMs)}
            </span>
          </li>
        ))}
      </ol>
    </section>
  );
}

function StageItem({ stage, number, current }: { stage: Stage; number: number; current: boolean }) {
  const hasItems = stage.items.length > 0;
  return (
    <li
      className={`stage stage-${stage.status}${current ? ' stage-current' : ''}`}
      aria-current={current ? 'step' : undefined}
    >
      <h3 className="stage-title">
        <span className="stage-number" aria-hidden="true">
          {number}
        </span>
        {stage.title}
      </h3>
      <p className="stage-status">
        <span aria-hidden="true">{STAGE_ICON[stage.status]}</span> {STAGE_STATUS_WORD[stage.status]}
      </p>

      {stage.bubbles.length > 0 && (
        <ul className="chip-list" aria-label="Bubbles searched">
          {stage.bubbles.map((b) => (
            <li key={b} className="chip">
              {b}
            </li>
          ))}
        </ul>
      )}

      {hasItems && (
        <ul className="evidence-list">
          {stage.items.map((item) => {
            const failed = item.status === 'error';
            return (
              <li key={item.key} className={failed ? 'evidence-failed' : undefined}>
                {failed ? (
                  <span>{item.label} bubble could not answer</span>
                ) : (
                  <>
                    <span>{item.label}</span>:{' '}
                    <span>
                      {item.count} {item.count === 1 ? 'item' : 'items'}
                    </span>
                    {item.relevance !== null && (
                      <>
                        {', '}
                        <span className="relevance" title={item.relevance.toFixed(2)}>
                          relevance {relevanceBand(item.relevance)}
                        </span>
                      </>
                    )}
                  </>
                )}
              </li>
            );
          })}
        </ul>
      )}

      {stage.noEvidence && <p className="stage-note">No relevant sources</p>}

      {stage.error && stage.status !== 'failed' && <p className="stage-note">{stage.error}</p>}
      {stage.status === 'failed' && (
        <p className="stage-error">{stage.error ?? 'This stage could not finish.'}</p>
      )}

      {stage.citations.length > 0 && (
        <ol className="citation-chips" aria-label="Cited sources">
          {stage.citations.map((c, i) => (
            <li key={c.item_id}>
              {c.url ? (
                <a className="chip chip-link" href={c.url} target="_blank" rel="noopener noreferrer">
                  <span aria-hidden="true">[{i + 1}]</span> {c.title || c.item_id}
                  <span className="sr-only"> (opens in a new tab)</span>
                </a>
              ) : (
                <span className="chip">
                  <span aria-hidden="true">[{i + 1}]</span> {c.title || c.item_id}
                </span>
              )}
            </li>
          ))}
        </ol>
      )}
    </li>
  );
}
