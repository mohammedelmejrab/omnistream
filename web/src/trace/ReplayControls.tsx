import { SPEEDS, type ReplayState, type Speed } from './replay';
import type { ReplayActions } from './hooks';

// Replay controls shared by the simple and advanced views (spec 10.2, 10.3, 10.4).
// Pause is always available (WCAG 2.2.2). Reduced motion: Play shows the whole run at once.

export interface ReplayControlsProps {
  state: ReplayState;
  /** Steps revealed right now (from useReplay). */
  cursor: number;
  actions: ReplayActions;
  total: number;
  reducedMotion: boolean;
  /** When true (live run), the controls describe the live position. */
  live: boolean;
}

export function ReplayControls({ state, cursor, actions, total, reducedMotion, live }: ReplayControlsProps) {
  const atStart = cursor === 0;
  const atEnd = cursor >= total;
  const playLabel = reducedMotion ? 'Show all steps' : state.playing ? 'Pause' : 'Play';
  const position = total === 0 ? 'No steps yet' : `Step ${cursor} of ${total}`;

  return (
    <div className="replay-controls" role="group" aria-label="Replay">
      <button type="button" className="pill-button" onClick={actions.restart} disabled={total === 0}>
        Replay
      </button>
      <button
        type="button"
        className="icon-button"
        onClick={actions.back}
        disabled={atStart || total === 0}
        aria-label="Step back"
      >
        ◀
      </button>
      <button
        type="button"
        className="pill-button"
        onClick={state.playing ? actions.pause : actions.play}
        disabled={total === 0 || (!reducedMotion && atEnd && !state.playing)}
        aria-pressed={reducedMotion ? undefined : state.playing}
      >
        {playLabel}
      </button>
      <button
        type="button"
        className="icon-button"
        onClick={actions.forward}
        disabled={atEnd || total === 0}
        aria-label="Step forward"
      >
        ▶
      </button>
      <label className="speed-label">
        Speed
        <select
          className="speed-select"
          value={String(state.speed)}
          onChange={(e) => actions.setSpeed(Number(e.target.value) as Speed)}
        >
          {SPEEDS.map((s) => (
            <option key={s} value={String(s)}>
              {s}×
            </option>
          ))}
        </select>
      </label>
      <span className="replay-position" aria-live="off">
        {live ? `Live · ${position}` : position}
      </span>
    </div>
  );
}
