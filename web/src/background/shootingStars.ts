// Shooting-star scheduler and pose (spec 11.3). Pure: time and randomness are
// passed in, so tests can drive it with a fake clock. At most one shot is live.

export const GAP_MIN_MS = 4000;
export const GAP_MAX_MS = 9000;
export const SHOT_MIN_MS = 800;
export const SHOT_MAX_MS = 1200;

/** Share of the travel that is tail, at most. */
const TAIL_FRACTION = 0.4;

export interface Vec {
  x: number;
  y: number;
}

export interface Shot {
  startMs: number;
  durationMs: number;
  from: Vec;
  /** Unit vector of travel, always down and to the right. */
  dir: Vec;
  lengthPx: number;
}

export interface ShotState {
  /** When the next shot may start. */
  nextAtMs: number;
  shot: Shot | null;
}

export interface Size {
  width: number;
  height: number;
}

function between(rand: () => number, min: number, max: number): number {
  return min + rand() * (max - min);
}

function gapMs(rand: () => number): number {
  return between(rand, GAP_MIN_MS, GAP_MAX_MS);
}

function newShot(now: number, rand: () => number, size: Size): Shot {
  const angle = (between(rand, 18, 45) * Math.PI) / 180;
  return {
    startMs: now,
    durationMs: between(rand, SHOT_MIN_MS, SHOT_MAX_MS),
    from: {
      x: between(rand, 0.05, 0.6) * size.width,
      y: between(rand, 0.02, 0.3) * size.height,
    },
    dir: { x: Math.cos(angle), y: Math.sin(angle) },
    lengthPx: between(rand, 160, 400),
  };
}

/** The first shot is due 4 to 9 seconds after `now`. */
export function createShots(now: number, rand: () => number): ShotState {
  return { nextAtMs: now + gapMs(rand), shot: null };
}

/** Starts a shot when one is due, ends it when it has run, and schedules the next gap. */
export function advanceShots(state: ShotState, now: number, rand: () => number, size: Size): ShotState {
  if (state.shot) {
    const end = state.shot.startMs + state.shot.durationMs;
    if (now < end) return state;
    return { nextAtMs: end + gapMs(rand), shot: null };
  }
  if (now < state.nextAtMs) return state;
  return { nextAtMs: state.nextAtMs, shot: newShot(now, rand, size) };
}

export interface ShotPose {
  head: Vec;
  tail: Vec;
  /** 0 to 1: fades in, peaks, fades out. */
  alpha: number;
}

/** Where a shot's head and tail are at `now`, or null when it is not running. */
export function shotPose(shot: Shot, now: number): ShotPose | null {
  const p = (now - shot.startMs) / shot.durationMs;
  if (p < 0 || p >= 1) return null;
  const eased = 1 - (1 - p) ** 3;
  const travel = shot.lengthPx * eased;
  const head = { x: shot.from.x + shot.dir.x * travel, y: shot.from.y + shot.dir.y * travel };
  const trail = Math.min(travel, shot.lengthPx * TAIL_FRACTION);
  const tail = { x: head.x - shot.dir.x * trail, y: head.y - shot.dir.y * trail };
  const alpha = Math.min(1, p / 0.15, (1 - p) / 0.3);
  return { head, tail, alpha };
}
