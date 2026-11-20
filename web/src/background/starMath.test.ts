import { describe, expect, it } from 'vitest';
import {
  advanceOrbit,
  rotateOffset,
  SWIRL_OMEGA,
  columnAlpha,
  COLUMN_ALPHA_FLOOR,
  EASE_BACK_MS,
  easeToward,
  GLOW_COUNT,
  lensRadius,
  makeStars,
  MOCHA_HEX,
  STAR_LAYERS,
  starPosition,
  twinkleFactor,
  WARP_IDLE_MS,
  WARP_MAX_PX,
  WARP_RADIUS_PX,
  warpBrightness,
  warpFalloff,
  warpOffset,
  warpTarget,
} from './starMath';

describe('cursor warp (lens-like displacement)', () => {
  it('is zero outside the warp radius and undefined-safe at the exact pointer', () => {
    expect(warpFalloff(WARP_RADIUS_PX)).toBe(0);
    expect(warpFalloff(WARP_RADIUS_PX + 40)).toBe(0);
    expect(warpOffset(0, 0, 0)).toEqual({ x: 0, y: 0 });
    expect(warpOffset(300, 0, 300)).toEqual({ x: 0, y: 0 });
  });

  it('is a strong lens: radius 110px and up to 22px displacement', () => {
    expect(WARP_RADIUS_PX).toBe(110);
    expect(WARP_MAX_PX).toBe(22);
  });

  it('pushes stars radially outward, never inward', () => {
    const cases: [number, number][] = [
      [20, 0],
      [0, -30],
      [-45, 60],
    ];
    for (const [dx, dy] of cases) {
      const d = Math.hypot(dx, dy);
      const off = warpOffset(dx, dy, d);
      // Offset is parallel to (dx, dy) with a positive scale: a radial push.
      expect(off.x * dx + off.y * dy).toBeGreaterThan(0);
      expect(Math.abs(off.x * dy - off.y * dx)).toBeLessThan(1e-9);
    }
  });

  it('is strongest near the cursor and falls off smoothly, capped at WARP_MAX_PX', () => {
    const samples = Array.from({ length: WARP_RADIUS_PX }, (_, i) => i + 1);
    const magnitudes = samples.map((d) => {
      const off = warpOffset(d, 0, d);
      return Math.hypot(off.x, off.y);
    });
    for (let i = 1; i < magnitudes.length; i += 1) {
      expect(magnitudes[i]!).toBeLessThanOrEqual(magnitudes[i - 1]! + 1e-9);
    }
    expect(magnitudes[0]).toBeGreaterThanOrEqual(0.9 * WARP_MAX_PX);
    expect(Math.max(...magnitudes)).toBeLessThanOrEqual(WARP_MAX_PX + 1e-9);
  });

  it('brightens stars near the cursor, never beyond full brightness', () => {
    expect(warpBrightness(0)).toBe(1);
    expect(warpBrightness(WARP_RADIUS_PX)).toBe(0);
    expect(warpBrightness(WARP_RADIUS_PX / 2)).toBeGreaterThan(0);
    expect(warpBrightness(WARP_RADIUS_PX / 2)).toBeLessThan(1);
  });
});

describe('lens cue', () => {
  it('grows stars inside the warp, up to 1.9x at the pointer, and leaves others alone', () => {
    expect(lensRadius(1, 0)).toBe(1);
    expect(lensRadius(1, 1)).toBeCloseTo(1.9, 6);
    expect(lensRadius(1, 0.5)).toBeGreaterThan(1);
    expect(lensRadius(1, 0.5)).toBeLessThan(1.9);
  });
});

describe('warp hold', () => {
  it('holds while the pointer is inside the page and moved recently', () => {
    expect(warpTarget(true, 1000, 0)).toBe(1);
    expect(warpTarget(true, 0 + WARP_IDLE_MS - 1, 0)).toBe(1);
  });

  it('lets go once the pointer has been idle for WARP_IDLE_MS (1.5 s)', () => {
    expect(WARP_IDLE_MS).toBe(1500);
    expect(warpTarget(true, WARP_IDLE_MS, 0)).toBe(0);
    expect(warpTarget(true, WARP_IDLE_MS + 500, 0)).toBe(0);
  });

  it('lets go as soon as the pointer leaves the page', () => {
    expect(warpTarget(false, 10, 9)).toBe(0);
  });

  it('is off before any pointer movement', () => {
    expect(warpTarget(true, 5000, -Infinity)).toBe(0);
  });
});

describe('ease back after the pointer stops', () => {
  it('returns to rest within about EASE_BACK_MS (about 200ms)', () => {
    let level = 1;
    for (let t = 0; t < EASE_BACK_MS; t += 16) level = easeToward(level, 0, 16);
    expect(level).toBeLessThan(0.05);
  });

  it('rises back toward full warp when the pointer returns', () => {
    const level = easeToward(0, 1, 16);
    expect(level).toBeGreaterThan(0);
    expect(level).toBeLessThan(1);
  });

  it('stays put when already at the target', () => {
    expect(easeToward(0, 0, 16)).toBe(0);
    expect(easeToward(1, 1, 16)).toBe(1);
  });
});

describe('star field', () => {
  it('is deterministic: the same seed gives the same stars every time', () => {
    expect(makeStars()).toEqual(makeStars());
  });

  it('changes positions when the seed changes', () => {
    expect(makeStars(7)).not.toEqual(makeStars(8));
  });

  it('places every star in the unit square, so positions scale with the viewport', () => {
    for (const s of makeStars()) {
      expect(s.u).toBeGreaterThanOrEqual(0);
      expect(s.u).toBeLessThan(1);
      expect(s.v).toBeGreaterThanOrEqual(0);
      expect(s.v).toBeLessThan(1);
      const p = starPosition(s, 1440, 900);
      expect(p.x).toBeLessThan(1440);
      expect(p.y).toBeLessThan(900);
    }
  });

  it('has about double the earlier density: 520, 220 and 70 stars', () => {
    expect(STAR_LAYERS.map((l) => l.count)).toEqual([520, 220, 70]);
  });

  it('has three depth layers of the configured counts, with a few glowing stars', () => {
    const stars = makeStars();
    expect(stars.length).toBe(STAR_LAYERS.reduce((n, l) => n + l.count, 0));
    for (const [i, layer] of STAR_LAYERS.entries()) {
      expect(stars.filter((s) => s.layer === i).length).toBe(layer.count);
    }
    expect(stars.filter((s) => s.glow).length).toBe(GLOW_COUNT);
    // Far stars are the smallest and dimmest, near stars the largest.
    expect(STAR_LAYERS[0]!.radius).toBeLessThan(STAR_LAYERS[1]!.radius);
    expect(STAR_LAYERS[1]!.radius).toBeLessThan(STAR_LAYERS[2]!.radius);
    expect(STAR_LAYERS[2]!.alpha[1]).toBeLessThanOrEqual(1);
  });

  it('uses only Catppuccin Mocha colours', () => {
    const allowed = new Set<string>(Object.values(MOCHA_HEX));
    for (const s of makeStars()) expect(allowed.has(s.color)).toBe(true);
  });

  it('twinkles quickly (0.5 to 1.8 Hz) with a clear amplitude', () => {
    for (const s of makeStars()) {
      expect(s.twinkleHz).toBeGreaterThanOrEqual(0.5);
      expect(s.twinkleHz).toBeLessThanOrEqual(1.8);
      for (let t = 0; t < 10; t += 0.37) {
        const f = twinkleFactor(s, t);
        expect(f).toBeGreaterThanOrEqual(0.55);
        expect(f).toBeLessThanOrEqual(1.45);
      }
    }
  });

  it('lifts the column fade near the pointer so the warp shows over the text column', () => {
    expect(columnAlpha(640, 1280, 1)).toBe(1);
    expect(columnAlpha(640, 1280, 0)).toBe(COLUMN_ALPHA_FLOOR);
    expect(columnAlpha(640, 1280, 0.5)).toBeGreaterThan(COLUMN_ALPHA_FLOOR);
  });

  it('dims stars behind the central column down to a floor, full at the edges', () => {
    expect(columnAlpha(640, 1280)).toBe(COLUMN_ALPHA_FLOOR);
    expect(columnAlpha(0, 1280)).toBe(1);
  });
});

describe('swirl: stars revolve around the pointer', () => {
  it('revolves faster nearer the pointer and not at all outside the lens', () => {
    expect(advanceOrbit(0, 1, 1000)).toBeCloseTo(SWIRL_OMEGA, 5);
    expect(advanceOrbit(0, 0.5, 1000)).toBeCloseTo(SWIRL_OMEGA / 2, 5);
    expect(advanceOrbit(0, 0, 1000)).toBe(0);
  });

  it('settles back to its home spot (a whole turn) once it leaves the lens', () => {
    let o = 2.5;
    for (let i = 0; i < 60; i += 1) o = advanceOrbit(o, 0, 50);
    expect(o).toBe(0);
    let spun = 4 * Math.PI + 0.4;
    for (let i = 0; i < 60; i += 1) spun = advanceOrbit(spun, 0, 50);
    expect(spun).toBeCloseTo(4 * Math.PI, 5);
  });

  it('rotates an offset around the origin and keeps its length', () => {
    const r = rotateOffset(10, 0, Math.PI / 2);
    expect(r.x).toBeCloseTo(0, 5);
    expect(r.y).toBeCloseTo(10, 5);
    expect(Math.hypot(r.x, r.y)).toBeCloseTo(10, 5);
  });
});
