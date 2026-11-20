import { describe, expect, it } from 'vitest';
import {
  advanceShots,
  createShots,
  GAP_MAX_MS,
  GAP_MIN_MS,
  SHOT_MAX_MS,
  SHOT_MIN_MS,
  shotPose,
} from './shootingStars';

const SIZE = { width: 1440, height: 900 };
const lowest = () => 0;
const highest = () => 0.999999;

describe('shooting star scheduler', () => {
  it('schedules the first shot 4 to 9 seconds after start, at random', () => {
    expect(createShots(1000, lowest).nextAtMs).toBe(1000 + GAP_MIN_MS);
    expect(createShots(1000, highest).nextAtMs).toBeCloseTo(1000 + GAP_MAX_MS, -1);
  });

  it('does not start a shot before its time', () => {
    const s = createShots(0, lowest);
    expect(advanceShots(s, GAP_MIN_MS - 1, lowest, SIZE).shot).toBeNull();
  });

  it('starts one shot at its time, lasting 0.8 to 1.2 seconds, heading down and right', () => {
    const s = advanceShots(createShots(0, lowest), GAP_MIN_MS, lowest, SIZE);
    expect(s.shot).not.toBeNull();
    const shot = s.shot!;
    expect(shot.durationMs).toBeGreaterThanOrEqual(SHOT_MIN_MS);
    expect(shot.durationMs).toBeLessThanOrEqual(SHOT_MAX_MS);
    expect(shot.dir.x).toBeGreaterThan(0);
    expect(shot.dir.y).toBeGreaterThan(0);
    expect(Math.hypot(shot.dir.x, shot.dir.y)).toBeCloseTo(1, 6);
    expect(shot.from.x).toBeGreaterThanOrEqual(0);
    expect(shot.from.x).toBeLessThanOrEqual(SIZE.width);
  });

  it('never runs more than one shot at a time', () => {
    const first = advanceShots(createShots(0, lowest), GAP_MIN_MS, lowest, SIZE);
    const midway = advanceShots(first, GAP_MIN_MS + 400, highest, SIZE);
    expect(midway.shot).toBe(first.shot);
    expect(midway.nextAtMs).toBe(first.nextAtMs);
  });

  it('clears the shot when it ends and schedules the next gap from the end', () => {
    const first = advanceShots(createShots(0, lowest), GAP_MIN_MS, lowest, SIZE);
    const end = GAP_MIN_MS + first.shot!.durationMs;
    const after = advanceShots(first, end, lowest, SIZE);
    expect(after.shot).toBeNull();
    expect(after.nextAtMs).toBe(end + GAP_MIN_MS);
  });

  it('keeps every gap between shots within 4 to 9 seconds over a long run', () => {
    let state = createShots(0, highest);
    let previousEnd: number | null = null;
    let starts = 0;
    for (let t = 0; t <= 10 * 60_000; t += 50) {
      const next = advanceShots(state, t, highest, SIZE);
      if (next.shot && next.shot !== state.shot) {
        starts += 1;
        if (previousEnd !== null) {
          const gap = next.shot.startMs - previousEnd;
          expect(gap).toBeGreaterThanOrEqual(GAP_MIN_MS);
          expect(gap).toBeLessThanOrEqual(GAP_MAX_MS + 50);
        }
      }
      if (state.shot && !next.shot) previousEnd = state.shot.startMs + state.shot.durationMs;
      state = next;
    }
    expect(starts).toBeGreaterThan(40);
  });
});

describe('shooting star variety', () => {
  it('varies angle and length: 18 to 45 degrees, 160 to 400px', () => {
    const angleDeg = (sh: { dir: { x: number; y: number } }) => (Math.atan2(sh.dir.y, sh.dir.x) * 180) / Math.PI;
    const low = advanceShots(createShots(0, lowest), GAP_MIN_MS, lowest, SIZE).shot!;
    const high = advanceShots(createShots(0, highest), GAP_MAX_MS, highest, SIZE).shot!;
    expect(angleDeg(low)).toBeCloseTo(18, 3);
    expect(angleDeg(high)).toBeCloseTo(45, 3);
    expect(low.lengthPx).toBeCloseTo(160, 3);
    expect(high.lengthPx).toBeCloseTo(400, 0);
  });

  it('still allows only one shot at a time on a 4 to 9 second gap', () => {
    const first = advanceShots(createShots(0, lowest), GAP_MIN_MS, lowest, SIZE);
    expect(advanceShots(first, GAP_MIN_MS + 1, highest, SIZE).shot).toBe(first.shot);
  });
});

describe('shooting star pose', () => {
  const shot = {
    startMs: 0,
    durationMs: 1000,
    from: { x: 200, y: 100 },
    dir: { x: Math.SQRT1_2, y: Math.SQRT1_2 },
    lengthPx: 300,
  };

  it('is absent before it starts and after it ends', () => {
    expect(shotPose(shot, -1)).toBeNull();
    expect(shotPose(shot, 1000)).toBeNull();
    expect(shotPose(shot, 1500)).toBeNull();
  });

  it('moves the head forward along the direction over its life', () => {
    const early = shotPose(shot, 200)!;
    const late = shotPose(shot, 800)!;
    const progressEarly = (early.head.x - shot.from.x) * shot.dir.x + (early.head.y - shot.from.y) * shot.dir.y;
    const progressLate = (late.head.x - shot.from.x) * shot.dir.x + (late.head.y - shot.from.y) * shot.dir.y;
    expect(progressLate).toBeGreaterThan(progressEarly);
    expect(progressLate).toBeLessThanOrEqual(shot.lengthPx + 1e-6);
  });

  it('fades in, peaks, and fades out; the tail trails behind the head', () => {
    const alphas = [0.05, 0.5, 0.9].map((p) => shotPose(shot, p * shot.durationMs)!.alpha);
    expect(alphas[0]).toBeLessThan(alphas[1]!);
    expect(alphas[2]).toBeLessThan(alphas[1]!);
    for (const a of alphas) {
      expect(a).toBeGreaterThanOrEqual(0);
      expect(a).toBeLessThanOrEqual(1);
    }
    const pose = shotPose(shot, 500)!;
    const tailDist = Math.hypot(pose.head.x - pose.tail.x, pose.head.y - pose.tail.y);
    expect(tailDist).toBeGreaterThan(0);
    // The tail sits back along the direction of travel.
    expect((pose.head.x - pose.tail.x) * shot.dir.x + (pose.head.y - pose.tail.y) * shot.dir.y).toBeGreaterThan(0);
  });
});
