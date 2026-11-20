# Agent S4 handoff 1: starfield background (round 4, web/), revision 2
Status: DONE. Revision 2 applied the orchestrator's warp and density decisions. All gates passed twice. No commits, no pushes, no .gitignore changes, no Claude attribution.
Skills: superpowers:test-driven-development (new behaviour tests written first and seen failing), superpowers:verification-before-completion (every claim below comes from a command run). No frontend-design skill is listed in this session.

## What was done
1. Starfield (`web/src/background/`):
   - `starMath.ts`: Mocha-only palette; three layers of 520 far, 220 mid and 70 near stars (6 near stars glow); seeded layout in viewport fractions; slow twinkle (0.1 to 0.35 Hz, ±15%).
   - Cursor warp (lens): radius 180px, max displacement 45px at the pointer, smoothstep falloff. Stars inside the lens brighten and grow (`lensRadius`, up to 1.9× at the pointer).
   - Warp hold: `warpTarget(inside, now, lastMove)`. Holds while the pointer is inside the page and moved within 1.5 s. Eases back over 200ms on leaving the page (`pointerleave` on `documentElement`, plus `blur`) or after 1.5 s idle.
   - `shootingStars.ts`: pure scheduler, gap 4 to 9 s, duration 0.8 to 1.2 s, one at a time. Angle 18 to 45 degrees and length 160 to 400px (was 22 to 38 degrees, 200 to 320px).
   - `StarCanvas.tsx`: one canvas, one rAF loop (animated mode, while visible and not paused). Static mode draws once and schedules nothing.
   - `StarBackground.tsx`: wrapper. Nothing rendered when the toggle is off; `static` under reduced motion.
   - Removed earlier: `DotBackground.tsx`, `DotCanvas.tsx`, `dotMath.ts`, `dotMath.test.ts`.
2. `HomePage.tsx` uses `StarBackground`. `components.css` uses `.star-background` and `.star-canvas`.
3. Spec `docs/superpowers/specs/2026-11-18-omnistream-ui-design.md`: section 11.3 now states the numbers above; decision 24 and the goal wording are updated (from revision 1).

## Tests
- Unit: 41 tests across `starMath.test.ts`, `shootingStars.test.ts` and `StarBackground.test.tsx`. New this revision: warp hold (inside and moved recently, 1.5 s idle, leaving the page, no movement yet), the lens cue, the radius and max constants, the 520/220/70 counts, shot angle and length ranges, and one-shot-at-a-time on the new ranges.
- E2E: `e2e/home-starfield.spec.ts`, 7 tests. The pointer now parks beside the heading (centre + 250px) for 300ms, which is inside the hold. Screenshots are full-size and zoomed clips.

## Gate results (run twice, from web/)
- `npx tsc -b --noEmit`: clean (both runs; the chain continued to vitest in each run)
- `npx vitest run`: 28 files, 239 tests, all pass (both runs)
- `npm run build`: clean (both runs)
- `npx playwright test`: 23 passed (both runs)

## Warp visibility (measured)
- Pixels changed within 180px of the pointer, pointer parked beside the heading at 1440×900: 1,144 of 130,321 (about 0.9%). The change is real but modest.
- Visible cues: the glow star at the top-right of the lens moved about 24 CSS px outward; the stars inside the lens grow and brighten. The field is sparse around the heading, so there are few stars to bend.
- The zoomed comparison is `web/e2e/screens/stars-home-1440-warp-compare.png` (left: no pointer; right: pointer parked).

## Frame cost (headless Chromium, DPR 2, 3 s with a pointer sweep; rAF callback time)
- 1440×900, 520+220+70 stars: avg 0.50 ms, p95 1.0 ms, max 3.7 ms.
- 1024×768: avg 0.38 ms, p95 0.5 ms, max 1.4 ms.
- Previous density (406 stars): avg 0.23 ms, p95 0.30 ms. The average and p95 are inside the 2 ms budget; the single 3.7 ms max is likely warm-up or GC, and I did not chase it.
- Excludes GPU raster and compositing, so this is an indication, not a pass on mid-range hardware.

## Rulings (where the brief or spec was silent)
1. The loop runs continuously while visible and not paused (twinkle and shots need frames). Spec 11.3 says so.
2. Reduced motion shows a static field (drawn once), not nothing.
3. The warp holds while the pointer is inside and moved within 1.5 s, then eases back over 200ms (the orchestrator's decision (a)).
4. Shot angle 18 to 45 degrees and length 160 to 400px (decision (d)).

## Concerns
1. **Warp still modest.** Decisions (a) to (c) were applied and the warp is measurably stronger, but on a sparse field around the heading it reads as subtle, not clearly visible. Options if you want it bolder: a visible lens ring (a faint Mocha ring at the warp radius), a denser near layer, or a larger radius. Each changes the look, so I did not add them unasked.
2. **Resting pointer.** Holding the pointer still inside the page keeps the warp for 1.5 s, then it releases. A pointer that rests for longer shows no warp.
3. **Max frame spike.** 3.7 ms at 1440×900 in one frame (see above). Average and p95 are fine.
4. **Perf on real hardware.** Headless only; needs a mid-range laptop check before it counts as a pass.
5. **Screenshots** in `web/e2e/screens/` are untracked (as in round 3). Decide whether they belong in the repo.
6. **Not touched:** B2's `/api/bubbles` and `/api/documents` path blockers, and `npm audit` (dev tooling only).

## Files touched (this round)
- New: `web/src/background/starMath.ts`, `starMath.test.ts`, `shootingStars.ts`, `shootingStars.test.ts`, `StarCanvas.tsx`, `StarBackground.tsx`, `StarBackground.test.tsx`, `web/e2e/home-starfield.spec.ts`
- Changed: `web/src/pages/HomePage.tsx`, `HomePage.test.tsx`, `web/src/theme/components.css`, the spec (section 11.3, decision 24, goal, Settings note, open items)
- Removed: `web/src/background/DotBackground.tsx`, `DotCanvas.tsx`, `dotMath.ts`, `dotMath.test.ts`
- Generated (untracked): `web/e2e/screens/stars-home-1440.png`, `stars-home-1440-pointer.png`, `stars-home-1440-pointer-zoom.png`, `stars-home-1440-warp-compare.png`, `stars-home-1024.png`, `stars-home-1024-pointer.png`
