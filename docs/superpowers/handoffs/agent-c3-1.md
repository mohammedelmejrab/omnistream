# Agent C3 handoff 1: trace and graph QA (web/src/trace, web/src/graph, web/e2e)

Status: DONE for the six items in agent-c2-1.md, plus the visual review. Two things are for the owners, not this agent: the page background token (Agent B's theme) and the entity labels (backend). See Concerns.

Spec: docs/superpowers/specs/2026-11-18-omnistream-ui-design.md (10.2, 10.3, 10.5, 11, 14).
Previous handoffs read: agent-c2-1.md (and via it agent-a-1, agent-b-1, agent-c-1).

## Done, by handoff item

1. **Refit on panel open and close.** `GraphCanvas` resize handler now refits when the user has not zoomed or panned. Once they have, it keeps their zoom and re-centres the focused node. Verified at 1440: the canvas ends at the panel's left edge (canvas 24 to 780, panel 780 to 1140) and the whole graph is visible.
2. **Timeline bars.** Checked, not changed. Widths are proportional to duration; bars under 4px are held at 4px by `min-width`. At 1440 the four long bars take most of the strip because the E2E server delays retrieval by 2 s, so they really are the longest steps. A log or capped scale would break "proportional", so I left it. Test added: min width 3.9px and width per ms equal across steps of 500 ms and up.
3. **Duplicate rows.** Backend seed and score steps have `bubble: null`. `stepLabels()` in `trace/model.ts` now takes the bubble from the nearest ancestor, so rows read "Picked entities for news" and "Scored finance evidence". A label that still repeats gets a number from its second copy on (`... (2)`), so earlier labels do not change during replay.
4. **Entity and chunk rows.** Group rows read "news: 2 entities and chunks" and their meta reads "Collapsed group of 2, select to expand". The Your question row's meta is "Start of the run" (it had repeated the label).
5. **Graph node list contrast.** Checked every token pair on the graph surfaces. One failed: subtext0 on surface1 (selected row) at 4.10:1. Selected meta now uses subtext1 (5.15:1). All others pass: list text 8.69, list meta on surface0 5.65, dimmed node border overlay1 on mantle 4.75, edge overlay0 3.59, lavender focus 7.0 to 9.8.
6. **Playwright suite.** `npm run build`, then `playwright test`: 16 passed (chat-to-trace 1, graph-viewer 2, layout 4, trace-view 9).

## Visual review fixes (trace simple view, Advanced graph, /app/graph)

- **Advanced graph, root cause of the clipping in item 1.** `NodeList` auto-focuses the first item, and the focus effect called `cy.center()` on it. That panned a fitted graph onto the first node. Now the view only pans when the focused node is hidden (off-canvas or under the panel). `keepVisible()` in `GraphCanvas.tsx`.
- **Advanced graph, layout.** dagre's own `fit` is off (we fit once, after `cy.resize()`). Node font 12 to 13px. Spacing tightened (nodeSep 18, rankSep 60). Group nodes 220px wide so the label is not cut off.
- **Advanced graph, under 1280px.** The stage had no height, so the overlay panel ran down the full page (screenshot 12,249px tall). The stage now has `height: max(420px, 62vh)` below 1280px. At under 768px the body no longer wraps (it had pushed the list 360px sideways).
- **Simple view.** Plural "1 item" (was "1 items"). Duration legend under the timeline, since the strip has no text: "1 Understood your question: 1 ms · 2 Searched bubbles: 1 ms · 3 Gathered evidence: 8.0 s · 4 Wrote answer: 3 ms". Strip has an 8px gap from the cards.
- **/app/graph.** It had no gutter (padding 24px, 16px under 1024px). Its canvas was 320px tall, so the graph zoomed to 2.5x and clipped on the right. It now has `height: max(420px, 100vh - 260px)`, and the first fit is correct (see the workaround note below). Under 768px it stacks.
- **Cytoscape first fit.** `GraphCanvas` calls `cy.resize()` before the first layout so the fit uses the final width.

## Files touched

Source:
- `web/src/graph/GraphCanvas.tsx` (refit on resize, `keepVisible`, `recentre`, `userMovedRef`, dagre `fit: false`, `cy.resize()` before first fit)
- `web/src/graph/cytoscape.ts` (font 13, group node width and label width)
- `web/src/graph/model.ts` (step labels via `stepLabels`, group label names the bubble, layout spacing)
- `web/src/graph/detail.ts` (`nodeMeta` for question and group)
- `web/src/graph/graph.css` (selected meta contrast, `.graph-page` gutter and height, stage height under 1280px, no wrap under 768px, graph page at 1023px and 767px)
- `web/src/trace/model.ts` (`bubbleOf`, `stepLabels`)
- `web/src/trace/AdvancedTrace.tsx` (timeline labels from `stepLabels`)
- `web/src/trace/SimpleView.tsx` (plural, duration legend, `formatDuration`)
- `web/src/trace/trace.css` (`.stage-durations`, `.timeline-stages` margin)

Tests:
- `web/src/graph/model.test.ts` (group label now names the bubble)
- `web/src/trace/model.test.ts` (`stepLabels`: bubble from ancestor, numbering from the second copy)
- `web/e2e/trace-view.spec.ts` (distinct rows and named groups; timeline min width and proportionality)
- `web/e2e/graph-viewer.spec.ts` (new: gutter, focused node inside canvas, Fit, no sideways scroll at 360px; screenshots)

Generated (not committed): `web/e2e/screens/*.png` (regenerated, including `graph-viewer-1440.png` and `graph-viewer-360.png`), `web/e2e/.results/`, `web/dist/`.

Not edited: `web/src/theme/*` (Agent B's), `web/src/api/*`, `.gitignore`, the backend.

## How to test

From `web/`:

```sh
./node_modules/.bin/tsc --noEmit -p tsconfig.json   # clean
./node_modules/.bin/vitest run                      # 25 files, 200 tests passed
npm run build                                       # clean
./node_modules/.bin/playwright test                 # 16 passed, starts the server itself on 8765
```

## Rulings

1. A focused node is only panned to when it is hidden (off-canvas or under the overlay panel). It is never centred just because it became focused. This is what keeps a fitted graph whole.
2. Fit leaves the view whole and is not sticky: the first fit and a later Fit button click can differ by about 0.3% in zoom (2.537 vs 2.530). The E2E asserts closeness to one decimal, not equality.
3. Timeline durations stay proportional. The 4px minimum is the only distortion.
4. Step labels: seed and score take the bubble from the nearest ancestor. Repeats are numbered from the second copy on, so a row's label never changes during replay.

## Concerns (for the owners)

1. **Page background (Agent B, theme).** `body` uses `--color-bg-deep` (`ctp-mantle`). Spec 11 says the background is Mocha **base**, with mantle and crust for depth. The trace and graph pages therefore show mantle. I did not change the shared token. Fix: decide with Agent B whether `--color-bg-deep` should be base. Pixel check: (24,24,37) at 1440 on the trace page.
2. **Graph labels on /app/graph (backend).** Entities show their names only in the global viewer, and there is no bubble on the label. Two "Alice" nodes (news and finance) look identical. Suggest adding the bubble to the label or the meta for each entity (`buildGlobalGraph` can do this on the frontend from `bubble`).
3. **Entity ids in the trace graph (backend, carried from C2).** Entity and chunk nodes inside an expanded group are labelled by id (`e-alice`) because steps carry no names.
4. **Graph text size at fit.** On a 1440 screen with the panel open, the Advanced graph fits at about 0.55x, so labels render at about 7 px. The list beside the graph has the same information and the zoom buttons enlarge it. Not changed; a smaller-scope fix would be a wider canvas or a horizontal layout.
5. **E2E server delay.** `OMNISTREAM_E2E_RETRIEVE_DELAY_MS=2000` makes retrieve steps dominate the timeline in every screenshot. That is an artefact of the test server, not a bug.
6. **Previous C2 note.** The "Expired trace returns 404" and the other backend gaps in agent-c2-1.md are unchanged.
7. **Generated output.** `web/e2e/.results/` and `web/e2e/screens/` are untracked generated files. Decide whether screenshots belong in the repo before commit.
