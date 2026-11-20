// Replay state for stored or live runs. The cursor counts how many ordered steps are
// revealed. A replay that is "pinned" to the end shows every step and follows new steps
// as they arrive (live runs), so the cursor is derived during render and needs no effect.
// Pure functions only; the React hook in hooks.ts drives the timer.

export const SPEEDS = [0.5, 1, 2, 4] as const;
export type Speed = (typeof SPEEDS)[number];

export interface ReplayState {
  /** Revealed step count while the user is moving the replay. Ignored while `follow` is set. */
  cursor: number;
  playing: boolean;
  speed: Speed;
  /** Pinned to the newest step: shows everything and follows steps as they arrive. */
  follow: boolean;
}

export function clampCursor(cursor: number, total: number): number {
  return Math.min(total, Math.max(0, cursor));
}

/** The number of steps to show right now. */
export function effectiveCursor(state: ReplayState, total: number): number {
  return state.follow ? total : clampCursor(state.cursor, total);
}

/** Opens pinned to the end, so the full result shows, and follows steps as they arrive. */
export function initialReplay(): ReplayState {
  return { cursor: 0, playing: false, speed: 1, follow: true };
}

/** Delay between auto-advanced steps. Faster at higher speeds. */
export function stepDelayMs(speed: Speed): number {
  return Math.round(900 / speed);
}

/** Restart from the first step and play. */
export function replayFromStart(state: ReplayState): ReplayState {
  return { ...state, cursor: 0, playing: true, follow: false };
}

/** Play from the current position; from the end, start again from the first step. */
export function play(state: ReplayState, total: number): ReplayState {
  const at = effectiveCursor(state, total);
  return { ...state, cursor: at >= total ? 0 : at, playing: true, follow: false };
}

/** Pause and keep the position where it is. */
export function pause(state: ReplayState, total: number): ReplayState {
  return { ...state, cursor: effectiveCursor(state, total), playing: false, follow: false };
}

export function stepBack(state: ReplayState, total: number): ReplayState {
  const cursor = clampCursor(effectiveCursor(state, total) - 1, total);
  return { ...state, cursor, playing: false, follow: cursor >= total };
}

export function stepForward(state: ReplayState, total: number): ReplayState {
  const cursor = clampCursor(effectiveCursor(state, total) + 1, total);
  return { ...state, cursor, playing: false, follow: cursor >= total };
}

export function seek(state: ReplayState, cursor: number, total: number): ReplayState {
  const c = clampCursor(cursor, total);
  return { ...state, cursor: c, playing: false, follow: c >= total };
}

export function setSpeed(state: ReplayState, speed: Speed): ReplayState {
  return { ...state, speed };
}

/** One timer tick while playing: reveal one more step, stop (and pin) at the end. */
export function tick(state: ReplayState, total: number): ReplayState {
  if (!state.playing) return state;
  const cursor = clampCursor(state.cursor + 1, total);
  return { ...state, cursor, playing: cursor < total, follow: cursor >= total };
}

/** Reveal everything and pin to the end (reduced-motion Play). */
export function showAll(state: ReplayState, total: number): ReplayState {
  return { ...state, cursor: total, playing: false, follow: true };
}
