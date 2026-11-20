import { describe, expect, it } from 'vitest';
import {
  clampCursor,
  effectiveCursor,
  initialReplay,
  pause,
  play,
  replayFromStart,
  seek,
  setSpeed,
  showAll,
  stepBack,
  stepDelayMs,
  stepForward,
  tick,
  type ReplayState,
} from './replay';

const mid = (over: Partial<ReplayState> = {}): ReplayState => ({
  cursor: 0,
  playing: false,
  speed: 1,
  follow: false,
  ...over,
});

describe('replay position', () => {
  it('opens pinned to the end, so the full result shows', () => {
    const s = initialReplay();
    expect(s.follow).toBe(true);
    expect(effectiveCursor(s, 5)).toBe(5);
  });

  it('a pinned replay follows new steps as they arrive, with no state change needed', () => {
    const s = initialReplay();
    expect(effectiveCursor(s, 2)).toBe(2);
    expect(effectiveCursor(s, 5)).toBe(5);
  });

  it('a moved replay keeps its place when new steps arrive', () => {
    expect(effectiveCursor(mid({ cursor: 2 }), 5)).toBe(2);
  });

  it('a moved replay is clamped if the total shrinks', () => {
    expect(effectiveCursor(mid({ cursor: 4 }), 3)).toBe(3);
  });

  it('clampCursor keeps values in 0..total', () => {
    expect(clampCursor(-1, 3)).toBe(0);
    expect(clampCursor(7, 3)).toBe(3);
  });
});

describe('replay actions', () => {
  it('play from the end starts again from the first step', () => {
    expect(play(initialReplay(), 5)).toMatchObject({ cursor: 0, playing: true, follow: false });
  });

  it('play from the middle resumes where the replay was', () => {
    expect(play(mid({ cursor: 2 }), 5)).toMatchObject({ cursor: 2, playing: true });
  });

  it('replayFromStart always starts at zero', () => {
    expect(replayFromStart(mid({ cursor: 4 }))).toMatchObject({ cursor: 0, playing: true });
  });

  it('tick reveals one more step and pins at the end', () => {
    let s = play(mid(), 3);
    s = tick(s, 3);
    expect(s).toMatchObject({ cursor: 1, playing: true, follow: false });
    s = tick(s, 3);
    s = tick(s, 3);
    expect(s).toMatchObject({ cursor: 3, playing: false, follow: true });
  });

  it('tick does nothing when paused', () => {
    const s = mid({ cursor: 1 });
    expect(tick(s, 3)).toBe(s);
  });

  it('pause freezes the position it is showing', () => {
    const s = pause(mid({ cursor: 2, playing: true }), 5);
    expect(s).toMatchObject({ cursor: 2, playing: false, follow: false });
  });

  it('step back from the pinned end lands on the step before the last', () => {
    expect(stepBack(initialReplay(), 4)).toMatchObject({ cursor: 3, playing: false, follow: false });
  });

  it('step forward is clamped, and reaching the end pins again', () => {
    expect(stepForward(mid({ cursor: 0 }), 3)).toMatchObject({ cursor: 1, follow: false });
    expect(stepForward(mid({ cursor: 2 }), 3)).toMatchObject({ cursor: 3, follow: true });
    expect(stepForward(initialReplay(), 3).cursor).toBe(3);
    expect(stepBack(mid({ cursor: 0 }), 3).cursor).toBe(0);
  });

  it('stepping stops playback', () => {
    expect(stepBack(mid({ cursor: 2, playing: true }), 3).playing).toBe(false);
  });

  it('seek clamps and pins only at the end', () => {
    expect(seek(mid(), 99, 4)).toMatchObject({ cursor: 4, follow: true });
    expect(seek(mid(), -3, 4)).toMatchObject({ cursor: 0, follow: false });
  });

  it('speed options map to shorter delays at higher speeds', () => {
    expect(stepDelayMs(1)).toBe(900);
    expect(stepDelayMs(4)).toBeLessThan(stepDelayMs(0.5));
    expect(setSpeed(mid(), 2).speed).toBe(2);
  });

  it('showAll reveals everything and pins (reduced-motion Play)', () => {
    expect(showAll(mid({ cursor: 1, playing: true }), 6)).toMatchObject({
      cursor: 6,
      playing: false,
      follow: true,
    });
  });
});
