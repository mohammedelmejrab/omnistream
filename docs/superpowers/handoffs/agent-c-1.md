# Agent C handoff 1: trace and graph (web/src/trace, web/src/graph)

Status: DONE for the scope in the brief (spec 10.2, 10.3, 10.4 client side, 10.5, trace parts of 11 and 14).
Not verified in a real browser. See "Not verified".

## Done

- Simple four-stage view (10.2): stages with icon plus word, bubble chips, evidence per bubble
  (Normal: one total; Agentic: one item per subagent), Low / Medium / High relevance (number on hover),
  failed bubble shown as "X bubble could not answer", "No relevant sources", numbered citation chips.
- Replay (10.2, 10.3): Replay, Play/Pause, step back and forward, speed 0.5x to 4x, position text.
  Replay is pinned to the end by default, so a finished run shows its full result on open.
  Timeline strip: stage durations in the simple view, step bars (120px, 4px minimum) in the advanced view.
- Advanced graph (10.3): Cytoscape through a React wrapper (`GraphCanvas`), deterministic dagre LR layout,
  entities and chunks collapsed to one count per bubble (expand from the canvas or the panel), cited items,
  answer path highlight with dimmed nodes (outline 4.6:1), running node pulses 3 cycles (static under reduced motion),
  zoom in, zoom out and fit as buttons, parallel DOM list (roving tabindex; Up/Down/Home/End; Enter opens panel),
  360px detail panel (focus moves in, Esc closes and returns focus), "Show in graph" and "Open source" for citations.
- Live (10.4): `useRunStream` / `RunStreamController` in `trace/stream.ts`. Opens SSE `GET /api/runs/{id}/events`
  when the run is running; handles `step`, `run`, `done`. Catch-up via `GET /api/runs/{id}` and `/steps` on open and
  on every reconnect. Reconnect backoff 1s, 2s, 4s, 8s, then 10s. Status only moves forward (a late "running"
  copy never overwrites a finished step). Stored finished runs never open a stream.
  Screen-reader text: one polite announcement per stage, failures in role="alert".
  Stored runs stay silent.
- Recovery states: not found (404) with focus on heading; expired (410) "Trace no longer available";
  failed, cancelled ("Stopped") and interrupted ("Interrupted when OmniStream restarted") runs keep their steps;
  empty answer shows "The model returned no answer." with a link back to the chat; reconnecting note.
- Global graph viewer `GraphPage` at `/app/graph` (10.5): bubble filter (refetch), node-kind filter, search by name
  (dims the rest), counts per bubble (loaded nodes), load more in pages of 300 (offset = nodes loaded so far),
  empty state linking to `/app/sources`, read-only detail panel, same list and zoom controls.
- Pure, tested helpers: ordering and upsert, relevance bands, simple-view model, replay reducer, announcements,
  graph model, answer path, detail model.
- Stored-steps fixture: `trace/fixtures/stored-runs.ts` (a normal run and an agentic run where one subagent fails).

## Files touched (36, all under web/src/trace and web/src/graph; plus this file)

Source (trace): types.ts, model.ts, replay.ts, hooks.ts, announce.ts, stream.ts, Timeline.tsx,
ReplayControls.tsx, SimpleView.tsx, AdvancedTrace.tsx, TracePage.tsx, trace.css, index.ts, fixtures/stored-runs.ts
Source (graph): model.ts, detail.ts, cytoscape.ts, GraphCanvas.tsx, NodeList.tsx, ZoomControls.tsx,
DetailPanel.tsx, GraphPage.tsx, graph.css, index.ts, testing/GraphCanvasStub.tsx
Tests: trace/{model,replay,hooks,announce,stream,TracePage}.test.ts(x); graph/{model,detail,layout,NodeList,GraphPage}.test.ts(x)

Nothing outside those paths was edited by me. `web/package.json`, `vite.config.ts`, `src/test/setup.ts`
and `api/*` are Agent B's and were used as they are. No commits made.

## Exports for the app shell (Agent B)

- `import { TracePage } from '@/trace'` (or `'../trace'`). Route: `/app/trace/:runId`.
  It reads `runId` or `run_id` from the params. It also takes a `runId` prop.
  It reads `?view=advanced`, and a localStorage preference `omnistream.trace.view`.
- `import { GraphPage } from '@/graph'`. Route: `/app/graph`.
- Both are page components. Each renders its own `h1` with `tabIndex={-1}`. Neither sets the document title.
- Recommend `React.lazy` for `GraphPage` as well. The graph chunk is about 179 KB gzipped (Cytoscape and dagre)
  and loads only for Advanced and `/app/graph`. The simple view does not load it.

## Rulings (spec was silent or ambiguous)

1. Contract types: re-exported from `web/src/api/types.ts` (Agent B's). `GraphNodeDto` and `GraphEdgeDto`
   are aliases of `GraphNode` and `GraphEdge`. The HTTP calls use Agent B's `api/runs.ts` and `api/graph.ts`
   and `ApiError` from `api/client.ts`.
2. Summary keys read from `Step.summary` (all optional, documented in `trace/types.ts`):
   `route.bubbles: string[]`, `retrieve.count`, `score.relevance` (0..1), `subagent.count`,
   `subagent.relevance`, `join.count`, `answer.citation_count`, `any.source_text`.
   Backend (Agent A) should match these, or the UI shows plain counts.
3. Expired trace: the UI expects HTTP 410 for an expired run, and shows "Trace no longer available".
   A 404 shows "Trace not found". If the backend returns 404 for expired runs too, the expired message never appears.
   Backend should use 410 for expired and 404 for unknown.
4. Live announcements do not show "of N" (the total is unknown while streaming). Finished runs show no
   announcements at all. Ruled to avoid reading a stale count.
5. Entity and chunk nodes are labelled with their ids. Step data carries `node_ids` only, with no names.
6. Global viewer: the API has no source parameter. The "Node kind" filter is client-side on the API `kind`
   field. The spec's "source" filter is not implemented as a server call. Needs a decision from the orchestrator.
   Counts per bubble are of loaded nodes, labelled "loaded".
7. Reduced motion: Play shows the whole run at once. Step back and forward still work. No pulse. CSS transitions off.
8. Empty answer on a finished run: "Retry from the chat" links to `/app/chat/{chat_id}`. The chat page resends.
9. Relevance bands: Low below 0.33, Medium below 0.66, High otherwise. The number is shown on hover (title)
   and in the advanced detail panel.
10. Advanced detail panel is an overlay on all widths. The spec wants it beside the graph at 1280px and up.
    Left as an overlay for now. Needs a layout decision (see concerns).
11. Stage status words: done, working, could not finish, no evidence, waiting (for not-yet-revealed stages).
12. Two colour sets: the trace CSS uses Agent B's `--ctp-*` tokens. Cytoscape styles need literal hex, so
    `graph/cytoscape.ts` holds Mocha values (`MOCHA`). They must stay in step with `theme/tokens.css`.
13. The view preference is per browser (localStorage). `?view=` overrides it and is kept in the URL.

## How to run

From `web/`:
- Tests: `./node_modules/.bin/vitest run src/trace src/graph`. All 11 files pass (122 tests).
  Summary from JSON reporter: 122 passed, 0 failed.
- Typecheck: `./node_modules/.bin/tsc --noEmit -p tsconfig.json`. Zero errors in `src/trace` and `src/graph`.
  Errors elsewhere, not mine (see blockers).
- Scratch bundle check: builds `trace/index.ts` and `graph/index.ts` with Vite (AdvancedTrace splits into its
  own 3 KB chunk; graph chunk 658 KB raw, 179 KB gzipped).

## Blockers and issues outside my scope (for Agent B or the orchestrator)

- `npm run typecheck` currently fails in files that are not mine:
  - `src/pages/ChatPage.tsx`: unused `titleFromQuestion`, missing `./NotFoundPage`, and two `setQueryData`
    updater type errors.
  - `vite.config.ts`: `node:url` and `process` need `@types/node`, which is not in `devDependencies`.
  These break `tsc -b` and therefore `npm run build`.
- No `src/main.tsx` yet, so `vite build` cannot produce the app. My modules were checked through a scratch Vite build.

## Not verified

- No browser run. Layout, no-horizontal-scroll at 1024, 768 and 200% zoom, and the visual check against the
  Mocha reference are not checked. Those need a manual pass or a Playwright check.
- The overlay "never covers the focused node" (WCAG 2.4.11) is only approximated: the active node is centred on
  the canvas, but a narrow overlay can still cover it.
- Focus and Back-button behaviour on route change belong to Agent B.
- Tests do not cover the Cytoscape canvas interactions themselves (tap, pan, zoom). They use a stub for the canvas,
  and the layout test runs the real dagre layout headless.

## Concerns

- Backend summary keys and the 410-for-expired behaviour (rulings 2 and 3) must match, or the UI degrades.
- The global viewer's "source" filter (ruling 6) has no API support.
- Bundle: 179 KB gzipped for the graph stack. Acceptable if lazy-loaded.
