# Agent B2 handoff 1: app shell, round 2 (web/)

Status: DONE, with the integration blockers listed under "Concerns" (two API paths the client calls do not exist on the server).
Scope: web/ app shell only. Did not touch web/src/trace or web/src/graph internals (Agent C), and no backend files (Agent A).
No commits, no pushes, no .gitignore changes, no Claude attribution.

Skills used: superpowers:test-driven-development (tests written first for each behaviour change), superpowers:verification-before-completion (every claim below is from a command run in this round).

## What was done (round-2 brief items)

1. Build and typecheck. `npm run build` and `npx tsc -b --noEmit` both pass. The round-1 errors (ChatPage unused var, NotFoundPage import, setQueryData typing, @types/node, src/main.tsx) were already resolved in the tree when this round started; checked, not re-edited. Agent C's `src/trace/fixtures/backend-runs.ts` briefly failed tsc during this round and passes now.
2. Run polling replaced by SSE. `src/chat/useRunWatch.ts` now drives `RunStreamController` from `src/trace/stream.ts` (C's, imported read-only). Snapshot first, then `GET /api/runs/{id}/events` while running; reconnect and catch-up come from the controller. The 1.2 s poll loop is gone. `onFinish` fires once per run, on the first terminal status seen.
   - `src/pages/ChatPage.test.tsx` now stubs EventSource and asserts the stream URL, `runPolls === 1` before open, and a closed stream after the answer.
   - Live check (browser, real HTTP, retrieval slowed to 3 s): one `GET .../events` request, no repeated `GET /api/runs/{id}` during the run, stage text "Searching News bubble, step 2" seen live, answer shown on finish.
3. Lazy loading. `GraphPage` and `TracePage` were already `React.lazy` in `src/router.tsx`. Build output confirms separate chunks (`trace-*.js`, `graph-*.js` 500 kB, `AdvancedTrace-*.js`). Added a document title for both (previously "OmniStream"): "Graph · OmniStream", "Trace · OmniStream".
4. Duplicate URL check. `SourceForm` now reads the server list (`GET /api/sources`) at submit time, not the list the panel loaded earlier, and falls back to the panel list if that read fails. A server 409 on create is handled: it re-reads the list, shows "Already added." with the link when it matches, otherwise shows the server message. Tests: 4 new cases in `src/sources/SourceForm.test.tsx`. Server does not return 409 yet (see Concerns).
5. Accessibility verification (details below): axe on 8 routes and 6 interactive states, horizontal overflow at 5 widths, titles and focus, contrast over the spec table, dot-canvas frame cost.
6. npm audit: report only (below).

## Fixes made during verification

- `src/api/chats.ts` `getChat`: the server returns the chat fields with a `messages` list, not `{chat, messages}`. The client now accepts both (`src/api/chats.test.ts`). Without this, a real chat page stayed on "Loading conversation" forever.
- `src/theme/components.css`: at 320 px the composer overflowed by 5 px. Narrow-screen rule (max-width 479.98px) tightens the composer padding and gaps. Overflow is gone at 320, 640, 768, 1024, 1440.
- `src/theme/components.css`: secondary text (`--color-text-muted`, subtext0) on surface1 hover/selected/active surfaces measured 4.10:1 (fails AA). Those containers now override the token to subtext1 (5.15:1) so muted text inside them inherits it. Affects mention options, mode options, chips, icon buttons, nav and rail links, active tabs. Axe on the mention list went from one color-contrast failure to none.
- `src/router.tsx`: document titles for lazy routes.

## Rulings (where the spec was silent or the brief left a choice)

1. Hover/selected/active surfaces (surface1) use subtext1 for secondary text. subtext0 measures 4.10:1 there. Spec section 11 table is unchanged for base and surface0.
2. `useRunWatch` keeps its `RunWatch` return shape so `RunBlock` and `MessageList` did not change. `error` is set while the stream is reconnecting; `gone` is set for 404 and 410.
3. Duplicate check uses the server list at submit time, with the panel list as fallback. A server 409 that matches a listed source shows "Already added."; any other 409 shows the server's message.
4. `getChat` accepts both response shapes (the server shape is the one we have).
5. Scratch-only aliases for `/api/bubbles` and `/api/documents` were used for browser checks (see Concerns). Nothing in the repo was changed for them.

## Accessibility verification

Scripts live in the scratchpad (not in the repo): `/private/tmp/claude-501/-Users-hf-Desktop-Semester-7-Capstone-Project-Capstone-omnistream/b491630a-b1ee-46a9-af8a-47e2306e0823/scratchpad/a11y/` (`check.mjs`, `states.mjs`, `perf.mjs`, `live.mjs`, `contrast.py`). Playwright (latest, with its Chromium build) and @axe-core/playwright are installed there, not in web/.

- axe-core, WCAG 2.0 A/AA, 2.1 A/AA, 2.2 AA, routes at 1440x900:
  - Home, chat, chats, sources, settings, trace, 404: no violations.
  - Graph (`/app/graph`): 1 `color-contrast` (serious). Element: `.node-list-item[role="option"] > .node-list-meta`, measured 4.09:1. It is in web/src/graph/graph.css (Agent C): selected rows are surface1 and `--g-subtext0` is subtext0. Fix is the same as ruling 1 (`--g-subtext0: var(--ctp-subtext1)` on selected or active rows).
  - Interactive states, all clean after the fix: home @-mention list, chat mode menu open with hover, chat sources sheet, chat delete dialog, sources add-feed form, settings replace-key.
  - One `html-has-lang` violation appeared once in a run and did not reproduce in two later full runs. `index.html` has `lang="en"`. Not chased further.
- Overflow (scrollWidth > clientWidth), all routes: none at 1440x900, 1024x768, 768x1024, 640x800, 320x640 after the composer fix. 640 wide is the 200% zoom approximation (1280 layout at 200%). Real browser zoom was not run.
- Titles and focus (1440): home "Ask · OmniStream", chat "<chat title> · OmniStream", chats, sources, graph, trace, settings, 404 all set. On first load focus is on the home textarea, and on other routes it is on body. Route-change focus to h1 is in AppShell and not re-tested this round.
- Contrast (computed from web/src/theme/tokens.css with the WCAG formula; script `contrast.py`):
  - All spec-table text pairs pass at or above the stated value (within 0.05).
  - overlay2 on surface0 computes 4.45, not 4.5 as the spec table says. It is not used for text (disabled text is exempt), so no change. Spec table should say 4.45.
  - subtext0 on surface1: 4.10, FAILS for text. Addressed by ruling 1.
  - text on surface1 6.31, subtext1 on surface1 5.15, lavender on surface0 7.03, mauve/blue on surface0 6.19/5.97.
- Dot canvas frame cost (headless Chromium, DPR 2, 60 pointer moves over ~3 s, timing each rAF callback; JS only):
  - 1440x900 (canvas 2880x1800 px): 137 frames, avg 0.83 ms, p95 1.8 ms, max 2.5 ms.
  - 1024x768: 133 frames, avg 0.49 ms, p95 0.7 ms, max 2.1 ms.
  - Average is inside the 2 ms budget. The p95 is close to it. This is an Apple-silicon headless run, not a mid-range laptop, and it does not include GPU raster or compositing cost. Treat it as an indication, not a pass on the target hardware.

## npm audit (report only; not applied)

`npm audit`: 6 high, 0 critical. Direct: `vite` (installed 8.3.8, advisory range >=6.3.0-beta.0), `vitest` (installed 5.1.0), `@vitejs/plugin-react` (installed 6.3.0). Transitive: `picomatch`, `tinyglobby`, `fdir`. All are dev tooling. `dist/` is not affected by them at runtime. `npm audit fix` and `--force` both propose downgrades (vite 6.2.7, vitest 3.1.4, plugin-react 5.2.0), which are breaking. Not applied. Recommend an upgrade pass with its own review, or accepting the dev-only risk for a local tool.

## Files touched (this round)

- `web/src/chat/useRunWatch.ts` (rewritten on the SSE controller)
- `web/src/pages/ChatPage.test.tsx` (EventSource stub, SSE assertions)
- `web/src/sources/SourceForm.tsx` (fresh duplicate check, 409 handling)
- `web/src/sources/SourceForm.test.tsx` (4 new cases)
- `web/src/api/chats.ts` (getChat accepts both shapes)
- `web/src/api/chats.test.ts` (new)
- `web/src/router.tsx` (lazy route titles)
- `web/src/theme/components.css` (narrow composer rule; subtext1 override on hover and selected surfaces)
- `docs/superpowers/handoffs/agent-b2-1.md` (this file)

## How to test

From `web/`:

```
npx tsc -b --noEmit          # passes
npm run build                # passes; graph and trace in their own chunks
npx vitest run               # 25 files, 197 tests, all pass
```

Live check (needs the venv): start the app with `make_app` from `tests/unit/test_ui_api.py` and `web/dist` (scratch script in the scratchpad `a11y/` folder and `serve/serve_ui.py`), then run `node check.mjs`, `node states.mjs`, `node perf.mjs`, `node live.mjs` against it.

## Concerns and blockers

1. BLOCKER for the real app (Agent A or orchestrator): the client calls `GET /api/bubbles` and `POST /api/documents`. The server only has `/bubbles` and `/documents`. Real effect: the bubble list is empty in chat, Sources, and Settings, and document upload returns 404. Browser checks used scratch aliases. Either add `/api/bubbles` and `/api/documents` aliases, or the client must change. I did not change the client path because the spec uses `/api/...` for all new endpoints.
2. Chat shape: the server returns the chat with `messages` flat. The client accepts both. Agent A should confirm which one is final so the contract types can be tightened.
3. Duplicate 409: the server does not return 409 for duplicate sources yet (Agent A's handoff). The client's fresh-list check catches it first, so the user-facing behaviour is correct; the 409 path is untested against a real server.
4. `POST /api/sources/test` does not exist on the server; the Test button shows "not available on this server yet". That is the designed fallback, flagged in round 1.
5. Graph node list contrast (see Accessibility). Agent C.
6. Dot canvas: average is inside budget on this machine; p95 is close to it. Needs a check on a mid-range laptop before it is called a pass.
7. Bundle: the graph chunk is 500 kB minified (160 kB gzipped). Vite warns on chunk size. Lazy-loaded, so it does not affect `/app` first load.
