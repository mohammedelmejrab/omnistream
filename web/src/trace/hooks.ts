import { useCallback, useEffect, useState } from 'react';
import {
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
  type Speed,
} from './replay';

export interface ReplayActions {
  play(): void;
  pause(): void;
  restart(): void;
  back(): void;
  forward(): void;
  seek(cursor: number): void;
  setSpeed(speed: Speed): void;
}

export interface ReplayView {
  state: ReplayState;
  /** Steps revealed right now (derived; no effect needed when new steps arrive). */
  cursor: number;
  actions: ReplayActions;
}

/**
 * Replay over an ordered list of steps. `total` is the number of steps known now.
 * The replay opens pinned to the end and follows new steps until the user moves it.
 * Under reduced motion, Play jumps to the end instead of animating (spec 14).
 */
export function useReplay(total: number, opts: { reducedMotion: boolean }): ReplayView {
  const { reducedMotion } = opts;
  const [state, setState] = useState<ReplayState>(initialReplay);

  // Timer: one step per delay while playing.
  useEffect(() => {
    if (!state.playing) return;
    const id = setTimeout(() => setState((s) => tick(s, total)), stepDelayMs(state.speed));
    return () => clearTimeout(id);
  }, [state.playing, state.cursor, state.speed, total]);

  const actions: ReplayActions = {
    play: useCallback(() => {
      setState((s) => (reducedMotion ? showAll(s, total) : play(s, total)));
    }, [reducedMotion, total]),
    pause: useCallback(() => setState((s) => pause(s, total)), [total]),
    restart: useCallback(() => {
      setState((s) => (reducedMotion ? showAll(s, total) : replayFromStart(s)));
    }, [reducedMotion, total]),
    back: useCallback(() => setState((s) => stepBack(s, total)), [total]),
    forward: useCallback(() => setState((s) => stepForward(s, total)), [total]),
    seek: useCallback((cursor: number) => setState((s) => seek(s, cursor, total)), [total]),
    setSpeed: useCallback((speed: Speed) => setState((s) => setSpeed(s, speed)), []),
  };

  return { state, cursor: effectiveCursor(state, total), actions };
}
