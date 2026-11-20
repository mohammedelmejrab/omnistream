import { act, renderHook } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { useReplay } from './hooks';

beforeEach(() => {
  vi.useFakeTimers();
});

afterEach(() => {
  vi.useRealTimers();
});

describe('useReplay', () => {
  it('plays one step per delay and pins at the end', () => {
    const { result } = renderHook(() => useReplay(3, { reducedMotion: false }));
    act(() => result.current.actions.restart());
    expect(result.current).toMatchObject({ cursor: 0 });
    expect(result.current.state.playing).toBe(true);

    act(() => vi.advanceTimersByTime(900));
    expect(result.current.cursor).toBe(1);
    act(() => vi.advanceTimersByTime(900));
    expect(result.current.cursor).toBe(2);
    act(() => vi.advanceTimersByTime(900));
    expect(result.current.cursor).toBe(3);
    expect(result.current.state.playing).toBe(false);
  });

  it('pause stops the timer where it is', () => {
    const { result } = renderHook(() => useReplay(5, { reducedMotion: false }));
    act(() => result.current.actions.restart());
    act(() => vi.advanceTimersByTime(900));
    act(() => result.current.actions.pause());
    act(() => vi.advanceTimersByTime(5000));
    expect(result.current.cursor).toBe(1);
    expect(result.current.state.playing).toBe(false);
  });

  it('a higher speed advances faster', () => {
    const { result } = renderHook(() => useReplay(5, { reducedMotion: false }));
    act(() => result.current.actions.setSpeed(4));
    act(() => result.current.actions.restart());
    act(() => vi.advanceTimersByTime(260));
    expect(result.current.cursor).toBe(1);
  });

  it('under reduced motion, Play shows the whole run without a timer', () => {
    const { result } = renderHook(() => useReplay(4, { reducedMotion: true }));
    act(() => result.current.actions.restart());
    expect(result.current.cursor).toBe(4);
    expect(result.current.state.playing).toBe(false);
    act(() => vi.advanceTimersByTime(5000));
    expect(result.current.cursor).toBe(4);
  });

  it('a live run shows new steps as they arrive, with no extra render needed', () => {
    const { result, rerender } = renderHook(
      ({ total }: { total: number }) => useReplay(total, { reducedMotion: false }),
      { initialProps: { total: 2 } },
    );
    expect(result.current.cursor).toBe(2);
    rerender({ total: 5 });
    expect(result.current.cursor).toBe(5);
  });

  it('once the user steps back, new steps do not move the replay', () => {
    const { result, rerender } = renderHook(
      ({ total }: { total: number }) => useReplay(total, { reducedMotion: false }),
      { initialProps: { total: 3 } },
    );
    act(() => result.current.actions.back());
    expect(result.current.cursor).toBe(2);
    rerender({ total: 6 });
    expect(result.current.cursor).toBe(2);
  });

  it('a stored run that loads after mount shows its end state on the first render with steps', () => {
    const { result, rerender } = renderHook(
      ({ total }: { total: number }) => useReplay(total, { reducedMotion: false }),
      { initialProps: { total: 0 } },
    );
    rerender({ total: 4 });
    expect(result.current.cursor).toBe(4);
  });
});
