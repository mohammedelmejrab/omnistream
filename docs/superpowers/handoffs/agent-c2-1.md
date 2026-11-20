# Agent C2 handoff 1: trace and graph QA (web/src/trace, web/src/graph, web/e2e)

Status: HANDOFF. Trace and graph are wired to the real backend and covered by a real-browser suite. Four layout fixes and one contrast check are still open (see Remaining).

Spec: docs/superpowers/specs/2026-11-18-omnistream-ui-design.md (sections 10.2 to 10.5, 11.1, 14).
Previous handoffs read: agent-a-1.md, agent-b-1.md, agent-c-1.md.

## Done

- Backend-shape fixes (frontend side only). The trace now reads what the real server emits, not only the keys in `trace/types.ts`:
  - Count: `count` if present, else `facts + chunks` (retrieve and subagent steps).
  - Relevance: `relevance` if present, else the best `top_facts[].score`. A subagent takes the best value among all steps under it in the step tree.
  - Stage 2 (Searched bubbles) follows `seed` steps when they exist, otherwise the first retrieve or subagent steps. Previously it showed "Waiting" on finished runs.
  - An empty stage on a finished run is now "Could not finish", not "Waiting".
- Overlay rule (spec 10.3, 11.1, WCAG 2.4.11):
  - At 1280px and up, the detail panel is a flex column beside the graph (360px).
  - Below 1280px, it overlays the graph. The focused node is centred in the uncovered part (pan by half of a 376px inset), so the overlay never covers it.
- `GraphCanvas` now has a ResizeObserver, so the canvas resizes when the panel opens or closes.
- Test hooks on the canvas element: `data-zoom` (zoom level, updated on zoom events) and `data-active-x` / `data-active-y` (focused node position in canvas pixels).
- Playwright 1.65.1 added as a dev dependency in `web/`, with Chromium installed. Config is `web/playwright.config.ts`.
- Playwright runs the real FastAPI app on port 8765 with a seeded temp database and the fake model runtime (`web/e2e/support/serve_e2e.py`). Retrieval is delayed 2 s so runs stay live long enough to watch.
- Suites (all in `web/e2e/`):
  - `chat-to-trace.spec.ts`: send a question, open the trace while it runs, check "Running", the live stage announcements, the answer, four Done stages, and replay to the end. This is the end-to-end test.
  - `trace-view.spec.ts`: simple view (stage words, bubble chips, citations, answer above stages), replay controls (Replay, step back and forward, speed, play and pause), advanced keyboard path (Home, End, arrows, Enter opens the panel, focus moves into it, Esc returns focus), zoom in, zoom out and fit with the zoom level checked, node target size of at least 24px, reduced motion (Show all steps, no pulse), and screenshots.
  - `layout.spec.ts`: no horizontal scroll on seven routes at 360, 640, 768, 1024, 1280 and 1440px; the panel is beside the graph at 1280 and up, overlays below it, and never covers the focused node; document title and focus on route change; screenshots of home and trace.
- Backend-shaped fixture `web/src/trace/fixtures/backend-runs.ts`, generated from the live server output (Normal: 5 steps; Agentic: 11 steps). Unit tests in `web/src/trace/backend-shape.test.ts` run the model against it.
- Last results: unit tests 128 passed; `tsc --noEmit` clean; Playwright 12 tests passed (chat-to-trace 1, trace-view 7, layout 4). After that run I changed only the screenshot path helper and reran just the screenshot test (passed). The rest were not rerun after the last edit.

## Remaining

1. **Refit Cytoscape on panel open and close.** `cy.resize()` runs, but the graph is not refit. In the 1440px screenshot the right side of the graph is clipped by the panel. Fix: call `fit` after the resize when the panel opens or closes (or only when the user has not zoomed).
2. **Timeline strip sizing (spec 10.3).** At 1440px the bars fill most of the strip instead of being proportional with a 4px minimum width. Timeline bars need proportional widths with a 4px minimum.
3. **Duplicate rows in the step list.** Seed and score steps show as "Picked bubbles" and "Scored evidence" once per bubble, which reads as duplicates. Show them once per bubble, or give each a bubble name.
4. **Unlabelled entity/chunk rows.** "2 entities and chunks" rows show with no name. Label them with the bubble name, or hide the row when the count is zero.
5. **Graph node list contrast.** Not checked. Spec 10.3 needs at least 3:1 non-text contrast for dimmed nodes. No contrast script has been run on the node list or the canvas.
6. Re-run all three Playwright specs after items 1 to 4 and check the screenshots again.

## Files touched

Source:
- `web/src/trace/model.ts` (count and relevance readers, stage 2 and empty-stage rules, `_run` parameter)
- `web/src/graph/detail.ts` (relevance from the step tree)
- `web/src/trace/AdvancedTrace.tsx` (overlay query, `PANEL_OVERLAY_INSET`, `overlayInset` prop)
- `web/src/graph/GraphCanvas.tsx` (`overlayInset`, ResizeObserver, `data-zoom`, `data-active-x/y`)
- `web/src/graph/graph.css` (1280px and up: panel beside the graph)

Tests and fixtures:
- `web/src/trace/fixtures/backend-runs.ts` (new)
- `web/src/trace/backend-shape.test.ts` (new)
- `web/playwright.config.ts` (new)
- `web/e2e/helpers.ts`, `chat-to-trace.spec.ts`, `trace-view.spec.ts`, `layout.spec.ts`, `support/serve_e2e.py` (new)
- `web/e2e/screens/*.png` (screenshots, generated)
- `web/e2e/.results/` (Playwright output, generated; add to `.gitignore` or delete before committing)
- `web/package.json` and `web/package-lock.json` (`@playwright/test` 1.65.1 in devDependencies)

Not edited: `web/src/api/*` and `web/src/theme/*` (Agent B's), and the backend.

Note: an early screenshot path produced a stray folder named `Semester%207` in `/Users/hf/Desktop`, created by my test run. I removed it. Nothing else was touched.

## How to run

From `web/`:

```sh
./node_modules/.bin/vitest run src/trace src/graph   # 12 files, 128 tests
./node_modules/.bin/tsc --noEmit -p tsconfig.json    # clean
npm run build                                        # vite build; tsc -b must also pass for this
./node_modules/.bin/playwright test                  # needs web/dist built first; starts the server itself
```

The Playwright server uses `../.venv/bin/python` (override with `OMNISTREAM_PYTHON`) and port 8765. Port 8000 is used by an unrelated process in this environment, so the E2E server avoids it.

Manual server (for A2 checks):

```sh
OMNISTREAM_E2E_RETRIEVE_DELAY_MS=2000 ../.venv/bin/python web/e2e/support/serve_e2e.py 8766
```

## Rulings

1. Step summary keys: the trace reads both the documented keys in `trace/types.ts` and the keys the backend emits today. The backend does not need to change to keep the UI working. This departs from the common-brief ruling that the backend adapts to `types.ts`; the orchestrator should confirm.
2. Relevance is taken from `score.relevance`, then `top_facts` scores, then the steps under a subagent. Route steps have no relevance.
3. Count is `count`, then facts plus chunks, then node ids.
4. Overlay inset is 376px (360px panel plus 16px gutter), applied only while the panel is open and below 1280px.
5. Reduced motion: Play becomes "Show all steps"; step back and forward still work.
6. The E2E suite uses a fake model runtime and a seeded temp database. It does not test a real provider or Neo4j.

## Backend gaps for A2

1. **Expired trace returns 404.** The backend returns 404 "Trace no longer available" for both unknown and expired runs. The common brief says expired returns 410. The UI shows "Trace not found" for the 404 case, so an expired trace shows the wrong message until this is fixed.
2. **User messages have no `run_id`.** `POST /api/chats/{id}/messages` returns `user_message.run_id: null`, and the stored user message also has `null`. The chat page only renders the run block (live progress and "Open live trace") for user messages with a `run_id`. Result: during a run the chat shows an empty answer block with "View trace" and no progress. Fix on the backend (set `run_id` on the user message), and the chat page will then show live progress. Agent B should also skip the empty assistant block while running.
3. **No `source_text`.** Steps never carry source text, so the detail panel's "Source text" section is always empty.
4. **No entity names.** Steps carry only node ids such as `e-alice`, so the graph labels are ids. Friendly names would need to be added to step summaries or the node list.
5. **Summary keys are mixed.** Retrieve and subagent summaries use `facts`, `chunks` and `top_facts`. Seed and score use `count` and `relevance`. Join uses `count: 0` even when it joined nothing. Answer has both `citations` and `citation_count`. Pick one set and document it in `types.ts`.
6. **Seed and score steps depend on the path.** In the Agentic run they appear under the join; in the Normal run, after retrieve. The UI handles both, but the step tree shape is not stable.

## Concerns

- The E2E suite runs against the same fake runtime as the unit tests. It shows the UI reads the real server's shape, not that real models produce correct evidence.
- `.results/` and `screens/` are generated output. Decide whether screenshots belong in the repo before committing.
- The graph viewer (`/app/graph`) still uses the overlay detail panel without the inset. Spec 10.5 does not say what it should do, so I left it alone.
