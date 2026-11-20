// Pure geometry, easing and star layout for the home-screen starfield (spec 11.3).
// Kept free of DOM access so it can be unit tested.

/** Catppuccin Mocha tints used by the field. Nothing else is drawn. */
export const MOCHA_HEX = {
  overlay0: '#6c7086',
  subtext0: '#a6adc8',
  text: '#cdd6f4',
  lavender: '#b4befe',
  blue: '#89b4fa',
  mauve: '#cba6f7',
  sapphire: '#74c7ec',
} as const;

/** Cursor warp: stars within this distance of the pointer are displaced. */
export const WARP_RADIUS_PX = 110;
/** Largest radial displacement, at the pointer. */
export const WARP_MAX_PX = 22;
/** The warp holds while the pointer is inside the page and has moved within this time. */
export const WARP_IDLE_MS = 1500;
/** Orbit speed at the pointer, rad/s. Stars further out revolve slower (smooth falloff). */
export const SWIRL_OMEGA = 1.3;
/** Trail length behind an orbiting star, in radians of arc at full strength. */
export const TRAIL_ANGLE = 0.3;
/** Time constant for a star's orbit to settle back to its home position. */
export const ORBIT_SETTLE_MS = 250;
/** Time for the warp to ease back after the pointer stops (about 200ms). */
export const EASE_BACK_MS = 200;

/** Central text column width (spec 25) and the fade band beside it. */
export const COLUMN_WIDTH_PX = 720;
export const COLUMN_FADE_PX = 80;
/** Opacity floor behind the column, so the text stays readable. */
export const COLUMN_ALPHA_FLOOR = 0.2;

/** Twinkle is slow and low amplitude: a factor within 1 ± TWINKLE_AMP. */
export const TWINKLE_AMP = 0.45;

export const STAR_SEED = 1;
export const GLOW_COUNT = 6;

export interface StarLayer {
  count: number;
  /** Star radius in CSS px. */
  radius: number;
  /** Base alpha range, [min, max]. */
  alpha: readonly [number, number];
  color: string;
}

/** Three depth layers: far stars are small and dim, near stars large and bright. */
export const STAR_LAYERS: readonly StarLayer[] = [
  { count: 520, radius: 0.6, alpha: [0.25, 0.5], color: MOCHA_HEX.overlay0 },
  { count: 220, radius: 0.95, alpha: [0.4, 0.7], color: MOCHA_HEX.subtext0 },
  { count: 70, radius: 1.4, alpha: [0.7, 1], color: MOCHA_HEX.text },
];

const GLOW_COLORS: readonly string[] = [MOCHA_HEX.lavender, MOCHA_HEX.blue, MOCHA_HEX.mauve, MOCHA_HEX.sapphire];

export interface Star {
  /** Position as a fraction of the viewport, so layout scales without reshuffling. */
  u: number;
  v: number;
  layer: number;
  radius: number;
  alpha: number;
  color: string;
  glow: boolean;
  twinkleHz: number;
  twinklePhase: number;
}

/** Small deterministic PRNG (mulberry32). Same seed, same sequence. */
function mulberry32(seed: number): () => number {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

/** Star layout in unit space. The same seed always gives the same field. */
export function makeStars(seed: number = STAR_SEED): Star[] {
  const rand = mulberry32(seed);
  const stars: Star[] = [];
  STAR_LAYERS.forEach((layer, index) => {
    const isNear = index === STAR_LAYERS.length - 1;
    for (let i = 0; i < layer.count; i += 1) {
      const u = rand();
      const v = rand();
      const alpha = layer.alpha[0] + (layer.alpha[1] - layer.alpha[0]) * rand();
      const twinkleHz = 0.5 + rand() * 1.3;
      const twinklePhase = rand() * Math.PI * 2;
      const glow = isNear && i < GLOW_COUNT;
      const color = glow ? (GLOW_COLORS[i % GLOW_COLORS.length] ?? layer.color) : layer.color;
      stars.push({ u, v, layer: index, radius: layer.radius, alpha, color, glow, twinkleHz, twinklePhase });
    }
  });
  return stars;
}

/** Pixel position of a star in a viewport. */
export function starPosition(star: Star, width: number, height: number): { x: number; y: number } {
  return { x: star.u * width, y: star.v * height };
}

/** Alpha multiplier for a star at time t (seconds). */
export function twinkleFactor(star: Star, tSec: number): number {
  return 1 + TWINKLE_AMP * Math.sin(2 * Math.PI * star.twinkleHz * tSec + star.twinklePhase);
}

/** 1 at the pointer, smoothly falling to 0 at WARP_RADIUS_PX. */
export function warpFalloff(distance: number): number {
  if (distance >= WARP_RADIUS_PX) return 0;
  const t = 1 - distance / WARP_RADIUS_PX;
  return t * t * (3 - 2 * t);
}

/** Radial, outward displacement from the pointer (lens-like bend). Zero at the exact pointer. */
export function warpOffset(dx: number, dy: number, distance: number): { x: number; y: number } {
  const f = warpFalloff(distance);
  if (f === 0 || distance === 0) return { x: 0, y: 0 };
  const scale = (WARP_MAX_PX * f) / distance;
  return { x: dx * scale, y: dy * scale };
}

/** Extra brightness for stars inside the warp, 0 to 1. */
export function warpBrightness(distance: number): number {
  return warpFalloff(distance);
}

/**
 * Moves `level` toward `target` with an exponential curve. The time constant
 * is a third of the duration, so the level is within about 5% after it.
 */
export function easeToward(level: number, target: number, dtMs: number, durationMs: number = EASE_BACK_MS): number {
  const tau = durationMs / 3;
  const k = 1 - Math.exp(-Math.max(0, dtMs) / tau);
  const next = level + (target - level) * k;
  return Math.abs(next - target) < 0.002 ? target : next;
}

/**
 * Warp target: 1 while the pointer is inside the page and moved within WARP_IDLE_MS,
 * otherwise 0 (the level then eases back over EASE_BACK_MS).
 */
export function warpTarget(inside: boolean, now: number, lastMoveMs: number): number {
  return inside && now - lastMoveMs < WARP_IDLE_MS ? 1 : 0;
}

/** Stars inside the warp grow with its brightness: 1x outside, up to 1.9x at the pointer. */
export function lensRadius(baseRadius: number, boost: number): number {
  return baseRadius * (1 + 0.9 * Math.min(1, Math.max(0, boost)));
}

/** Alpha multiplier so stars fade out behind the central column. `reveal` (0 to 1) lifts the fade near the pointer. */
export function columnAlpha(x: number, width: number, reveal = 0): number {
  const base = columnAlphaBase(x, width);
  return base + (1 - base) * Math.min(1, Math.max(0, reveal));
}

function columnAlphaBase(x: number, width: number): number {
  const edge = Math.abs(x - width / 2) - COLUMN_WIDTH_PX / 2;
  if (edge <= 0) return COLUMN_ALPHA_FLOOR;
  if (edge >= COLUMN_FADE_PX) return 1;
  return COLUMN_ALPHA_FLOOR + (1 - COLUMN_ALPHA_FLOOR) * (edge / COLUMN_FADE_PX);
}

/** A #rrggbb colour with an alpha, for canvas strings. */
export function withAlpha(hex: string, alpha: number): string {
  const n = Number.parseInt(hex.slice(1), 16);
  const r = (n >> 16) & 255;
  const g = (n >> 8) & 255;
  const b = n & 255;
  return `rgba(${r}, ${g}, ${b}, ${Math.min(1, Math.max(0, alpha)).toFixed(3)})`;
}

const TWO_PI = Math.PI * 2;

/**
 * Advances one star's orbit angle. Inside the lens (strength f above 0) it revolves around the
 * pointer, faster near it. Outside, it settles to the nearest whole turn, which is its home spot.
 */
export function advanceOrbit(orbit: number, strength: number, dtMs: number): number {
  const dt = Math.max(0, dtMs);
  if (strength > 0.002) return orbit + SWIRL_OMEGA * strength * (dt / 1000);
  const home = Math.round(orbit / TWO_PI) * TWO_PI;
  const next = orbit + (home - orbit) * (1 - Math.exp(-dt / ORBIT_SETTLE_MS));
  return Math.abs(next - home) < 0.001 ? home : next;
}

/** Rotates the offset (dx, dy) by `angle` radians. */
export function rotateOffset(dx: number, dy: number, angle: number): { x: number; y: number } {
  const c = Math.cos(angle);
  const sn = Math.sin(angle);
  return { x: dx * c - dy * sn, y: dx * sn + dy * c };
}
