import { useEffect, useRef, type ReactElement } from 'react';
import { advanceShots, createShots, shotPose, type ShotState } from './shootingStars';
import {
  advanceOrbit,
  columnAlpha,
  easeToward,
  lensRadius,
  makeStars,
  MOCHA_HEX,
  rotateOffset,
  TRAIL_ANGLE,
  twinkleFactor,
  WARP_RADIUS_PX,
  warpFalloff,
  warpOffset,
  warpTarget,
  withAlpha,
} from './starMath';

export type StarMode = 'animated' | 'static';

interface StarCanvasProps {
  /** animated: twinkle, cursor warp and shooting stars. static: one drawn frame, no loop. */
  mode: StarMode;
  /** Paused while a run streams. */
  paused?: boolean;
}

const MAX_DPR = 2;
const GLOW_RADIUS_PX = 7;

/**
 * One canvas. In animated mode a single requestAnimationFrame loop runs while the
 * home screen is visible and not paused; it stops when the tab is hidden or a run
 * streams (spec 11.3). Static mode draws one frame and schedules nothing.
 */
export function StarCanvas({ mode, paused = false }: StarCanvasProps): ReactElement {
  const ref = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = ref.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const animated = mode === 'animated';
    const stars = makeStars();
    const orbit = new Float32Array(stars.length);
    let lastDt = 16;
    let width = 0;
    let height = 0;
    let inside = false;
    let px = -1e6;
    let py = -1e6;
    let movedPending = false;
    let lastMove = -Infinity;
    let level = 0;
    let shots: ShotState | null = null;
    let lastNow = 0;
    let lastFrame: number | null = null;
    let raf = 0;

    const resize = (): void => {
      const dpr = Math.min(window.devicePixelRatio || 1, MAX_DPR);
      width = window.innerWidth;
      height = window.innerHeight;
      canvas.width = Math.round(width * dpr);
      canvas.height = Math.round(height * dpr);
      canvas.style.width = `${width}px`;
      canvas.style.height = `${height}px`;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    };

    const draw = (now: number): void => {
      lastNow = now;
      ctx.clearRect(0, 0, width, height);
      const tSec = now / 1000;
      for (let i = 0; i < stars.length; i += 1) {
        const s = stars[i]!;
        const bx = s.u * width;
        const by = s.v * height;
        let x = bx;
        let y = by;
        let boost = 0;
        let headR = 0;
        let headA = 0;
        let trailArc = 0;
        const dx = bx - px;
        const dy = by - py;
        const d = level > 0 || orbit[i] !== 0 ? Math.hypot(dx, dy) : Infinity;
        const strength = d < WARP_RADIUS_PX ? warpFalloff(d) * level : 0;
        orbit[i] = animated ? advanceOrbit(orbit[i]!, strength, lastDt) : 0;
        if (d < WARP_RADIUS_PX || orbit[i] !== 0) {
          const push = d < WARP_RADIUS_PX ? warpOffset(dx, dy, d) : { x: 0, y: 0 };
          const base = { x: dx + push.x * level, y: dy + push.y * level };
          const head = rotateOffset(base.x, base.y, orbit[i]!);
          x = px + head.x;
          y = py + head.y;
          boost = strength;
          if (strength > 0.05) {
            headR = Math.hypot(head.x, head.y);
            headA = Math.atan2(head.y, head.x);
            trailArc = TRAIL_ANGLE * strength;
          }
        }
        const twinkle = animated ? twinkleFactor(s, tSec) : 1;
        const alpha = Math.min(1, s.alpha * twinkle + 0.6 * boost) * columnAlpha(bx, width, boost);
        const radius = lensRadius(s.radius, boost);
        ctx.globalAlpha = alpha;
        if (s.glow) {
          const glow = ctx.createRadialGradient(x, y, 0, x, y, GLOW_RADIUS_PX);
          glow.addColorStop(0, withAlpha(s.color, 0.5));
          glow.addColorStop(1, withAlpha(s.color, 0));
          ctx.globalAlpha = 1;
          ctx.fillStyle = glow;
          ctx.beginPath();
          ctx.arc(x, y, GLOW_RADIUS_PX, 0, Math.PI * 2);
          ctx.fill();
          ctx.globalAlpha = alpha;
        }
        if (trailArc > 0) {
          // A comet tail: three arc pieces along the orbit, fading away from the head.
          ctx.strokeStyle = s.color;
          ctx.lineCap = 'round';
          ctx.lineWidth = Math.max(0.7, radius * 0.8);
          for (let k = 0; k < 3; k += 1) {
            ctx.globalAlpha = alpha * (0.5 - 0.17 * k);
            ctx.beginPath();
            ctx.arc(px, py, headR, headA - (trailArc * (k + 1)) / 3, headA - (trailArc * k) / 3);
            ctx.stroke();
          }
          ctx.globalAlpha = alpha;
          // A soft halo makes the moving head read as a star, not a dash.
          const halo = ctx.createRadialGradient(x, y, 0, x, y, radius * 4);
          halo.addColorStop(0, withAlpha(s.color, 0.35 * boost));
          halo.addColorStop(1, withAlpha(s.color, 0));
          ctx.globalAlpha = 1;
          ctx.fillStyle = halo;
          ctx.beginPath();
          ctx.arc(x, y, radius * 4, 0, Math.PI * 2);
          ctx.fill();
          ctx.globalAlpha = alpha;
        }
        ctx.fillStyle = s.color;
        ctx.beginPath();
        ctx.arc(x, y, radius, 0, Math.PI * 2);
        ctx.fill();
      }
      ctx.globalAlpha = 1;

      const pose = shots?.shot ? shotPose(shots.shot, now) : null;
      if (pose && pose.alpha > 0) {
        const grad = ctx.createLinearGradient(pose.tail.x, pose.tail.y, pose.head.x, pose.head.y);
        grad.addColorStop(0, withAlpha(MOCHA_HEX.sapphire, 0));
        grad.addColorStop(1, withAlpha(MOCHA_HEX.text, pose.alpha));
        ctx.strokeStyle = grad;
        ctx.lineWidth = 1.4;
        ctx.lineCap = 'round';
        ctx.beginPath();
        ctx.moveTo(pose.tail.x, pose.tail.y);
        ctx.lineTo(pose.head.x, pose.head.y);
        ctx.stroke();
      }
    };

    const frame = (now: number): void => {
      raf = 0;
      if (paused || document.hidden) return;
      const dt = lastFrame === null ? 16 : now - lastFrame;
      lastFrame = now;
      if (movedPending) {
        lastMove = now;
        movedPending = false;
      }
      const target = warpTarget(inside, now, lastMove);
      level = easeToward(level, target, dt);
      lastDt = dt;
      shots = shots
        ? advanceShots(shots, now, Math.random, { width, height })
        : createShots(now, Math.random);
      draw(now);
      raf = requestAnimationFrame(frame);
    };

    const start = (): void => {
      if (!animated || raf || paused || document.hidden) return;
      lastFrame = null;
      raf = requestAnimationFrame(frame);
    };

    const stop = (): void => {
      if (raf) cancelAnimationFrame(raf);
      raf = 0;
    };

    const onMove = (e: PointerEvent): void => {
      px = e.clientX;
      py = e.clientY;
      inside = true;
      movedPending = true;
      start();
    };
    const onLeave = (): void => {
      inside = false;
    };
    const onVisibility = (): void => {
      if (document.hidden) {
        stop();
        lastFrame = null;
      } else if (animated) {
        start();
      } else {
        draw(lastNow);
      }
    };
    const onResize = (): void => {
      resize();
      draw(lastNow);
    };

    resize();
    draw(0);
    if (animated) {
      window.addEventListener('pointermove', onMove, { passive: true });
      document.documentElement.addEventListener('pointerleave', onLeave);
      window.addEventListener('blur', onLeave);
    }
    window.addEventListener('resize', onResize);
    document.addEventListener('visibilitychange', onVisibility);
    start();

    return () => {
      stop();
      window.removeEventListener('pointermove', onMove);
      document.documentElement.removeEventListener('pointerleave', onLeave);
      window.removeEventListener('blur', onLeave);
      window.removeEventListener('resize', onResize);
      document.removeEventListener('visibilitychange', onVisibility);
    };
  }, [mode, paused]);

  return <canvas ref={ref} className="star-canvas" aria-hidden="true" />;
}
