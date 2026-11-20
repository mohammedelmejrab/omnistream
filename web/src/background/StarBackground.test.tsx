import { act, fireEvent, render } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { GAP_MIN_MS } from './shootingStars';
import { StarBackground } from './StarBackground';

type Frame = (now: number) => void;

/** A 2D context that records calls, so tests can see what a frame drew. */
function stubContext() {
  const gradient = () => ({ addColorStop: vi.fn() });
  const ctx = {
    arc: vi.fn(),
    fill: vi.fn(),
    beginPath: vi.fn(),
    clearRect: vi.fn(),
    setTransform: vi.fn(),
    moveTo: vi.fn(),
    lineTo: vi.fn(),
    stroke: vi.fn(),
    fillRect: vi.fn(),
    createRadialGradient: vi.fn(gradient),
    createLinearGradient: vi.fn(gradient),
    globalAlpha: 1,
    fillStyle: '',
    strokeStyle: '',
    lineWidth: 1,
    lineCap: 'butt',
  };
  vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockImplementation(
    () => ctx as unknown as CanvasRenderingContext2D,
  );
  return ctx;
}

/** requestAnimationFrame that only runs when the test says so. */
function stubFrames() {
  let queue: Frame[] = [];
  vi.stubGlobal(
    'requestAnimationFrame',
    vi.fn((cb: Frame) => {
      queue.push(cb);
      return queue.length;
    }),
  );
  vi.stubGlobal('cancelAnimationFrame', vi.fn());
  return {
    pending: () => queue.length,
    run(now: number) {
      const current = queue;
      queue = [];
      for (const cb of current) cb(now);
    },
  };
}

function stubMotion(reduced: boolean) {
  vi.stubGlobal('matchMedia', (query: string) => ({
    matches: reduced && query.includes('reduce'),
    media: query,
    addEventListener: () => undefined,
    removeEventListener: () => undefined,
  }));
}

function setHidden(hidden: boolean) {
  Object.defineProperty(document, 'hidden', { configurable: true, get: () => hidden });
}

afterEach(() => {
  setHidden(false);
  vi.restoreAllMocks();
});

describe('StarBackground', () => {
  it('renders nothing when the Settings toggle is off', () => {
    stubMotion(false);
    const frames = stubFrames();
    const { container } = render(<StarBackground enabled={false} />);
    expect(container.querySelector('canvas')).toBeNull();
    expect(frames.pending()).toBe(0);
  });

  it('keeps one animation loop running while enabled and visible', () => {
    stubMotion(false);
    const ctx = stubContext();
    const frames = stubFrames();
    const { container } = render(<StarBackground enabled />);
    expect(container.querySelector('canvas')).not.toBeNull();
    expect(frames.pending()).toBe(1);
    ctx.arc.mockClear();
    frames.run(0);
    expect(ctx.arc.mock.calls.length).toBeGreaterThan(300);
    expect(frames.pending()).toBe(1);
  });

  it('animates even when the device asks for reduced motion', () => {
    stubMotion(true);
    const ctx = stubContext();
    const frames = stubFrames();
    render(<StarBackground enabled />);
    expect(ctx.arc.mock.calls.length).toBeGreaterThan(300);
    expect(frames.pending()).toBe(1);
  });

  it('stops scheduling frames while a run streams and resumes after', () => {
    stubMotion(false);
    stubContext();
    const frames = stubFrames();
    const { rerender } = render(<StarBackground enabled paused />);
    expect(frames.pending()).toBe(0);
    rerender(<StarBackground enabled paused={false} />);
    expect(frames.pending()).toBe(1);
  });

  it('pauses while the tab is hidden and resumes when it is shown again', () => {
    stubMotion(false);
    stubContext();
    const frames = stubFrames();
    setHidden(true);
    render(<StarBackground enabled />);
    expect(frames.pending()).toBe(0);
    setHidden(false);
    act(() => {
      document.dispatchEvent(new Event('visibilitychange'));
    });
    expect(frames.pending()).toBe(1);
  });

  it('shows a shooting star after the first gap, not before', () => {
    stubMotion(false);
    const ctx = stubContext();
    vi.spyOn(Math, 'random').mockReturnValue(0);
    const frames = stubFrames();
    render(<StarBackground enabled />);
    frames.run(0); // first frame starts the schedule
    frames.run(GAP_MIN_MS - 1);
    expect(ctx.createLinearGradient).not.toHaveBeenCalled();
    frames.run(GAP_MIN_MS); // the shot starts here, with zero alpha
    frames.run(GAP_MIN_MS + 400); // mid-flight, visible
    expect(ctx.createLinearGradient).toHaveBeenCalled();
  });

  it('warps the field when the pointer moves over it', () => {
    stubMotion(false);
    const ctx = stubContext();
    const frames = stubFrames();
    render(<StarBackground enabled />);
    frames.run(0);

    const positions = (): string => ctx.arc.mock.calls.map((c) => `${c[0].toFixed(2)},${c[1].toFixed(2)}`).join('|');
    ctx.arc.mockClear();
    frames.run(16);
    const resting = positions();

    fireEvent(window, new MouseEvent('pointermove', { clientX: 700, clientY: 450 }));
    ctx.arc.mockClear();
    frames.run(32);
    expect(positions()).not.toBe(resting);
  });

  it('cancels the pending frame on unmount', () => {
    stubMotion(false);
    stubContext();
    const frames = stubFrames();
    const { unmount } = render(<StarBackground enabled />);
    expect(frames.pending()).toBe(1);
    unmount();
    expect(window.cancelAnimationFrame).toHaveBeenCalled();
  });

  it('is decorative: aria-hidden and not focusable', () => {
    stubMotion(false);
    stubContext();
    stubFrames();
    const { container } = render(<StarBackground enabled />);
    const canvas = container.querySelector('canvas')!;
    expect(canvas).toHaveAttribute('aria-hidden', 'true');
    expect(canvas).not.toHaveAttribute('tabindex');
    expect(container.firstElementChild).toHaveAttribute('aria-hidden', 'true');
  });
});
