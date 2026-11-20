# Agent B handoff 1: app shell (web/)

Status: DONE for the app shell, with the concerns listed below. Agent C's trace and graph code is wired in but still has type errors of its own.

Spec: docs/superpowers/specs/2026-11-18-omnistream-ui-design.md (sections 5, 6, 7, 8, 9, 10.6, 11, 11.1-11.3, 13)
Brief: /private/tmp/claude-501/-Users-hf-Desktop-Semester-7-Capstone-Project-Capstone-omnistream/613c4a34-45cb-4077-ac8f-68dff433240d/scratchpad/common-brief.md

## What is built

- Scaffold: `web/` with Vite 8, React 19, React Router 8, TypeScript (strict, noUncheckedIndexedAccess, exactOptionalPropertyTypes), Vitest 5 with jsdom and Testing Library. `base: '/app/'`, `build.outDir: 'dist'`, dev proxy `/api` to `OMNISTREAM_API` (default `http://127.0.0.1:8000`).
- Theme: Catppuccin Mocha tokens (`web/src/theme/tokens.css`), radius scale (r-xs 4, r-sm 8, r-md 12, r-lg 20, r-pill), global and component CSS, reduced-motion overrides, visible Lavender focus ring.
- Routing (`web/src/router.tsx`): `/app`, `/app/chat/:chatId`, `/app/chats`, `/app/sources`, `/app/graph`, `/app/trace/:runId`, `/app/settings`, 404 for unknown routes, and a route error page for server-down. Trace and graph are lazy-loaded from Agent C's `@/trace` and `@/graph`.
- Shell: skip link, primary nav, per-route document title, focus moves to the route's `h1` on route change (not on first load), Recent rail on chat pages only (collapses below 1024px).
- Chat home: "Where should we start?", composer (Enter sends, Shift+Enter newline, 6-line growth, pill to 20px radius when wrapped, 20,000 character limit with counter), `+` opens the Sources sheet, `@` mention combobox (ARIA combobox and listbox, bubbles and sources), mode selector (menu button with radio group, descriptions in the menu, aria-describedby), suggestions, Recent row (hidden when empty, See all).
- Answer loop: create chat, send question with mode and optional bubble_ids, navigate to the chat with the run id. The chat page follows the latest run by polling `GET /api/runs/{id}` and `/steps` every 1.2s until terminal, then reloads the chat. Statuses: running (live polite announcement per stage), ok (answer block with mode badge and numbered citations), failed (alert, readable error, Retry), empty answer (shown as failed with "The model returned no answer"), cancelled ("Stopped"), interrupted ("Interrupted when OmniStream restarted"), expired trace ("Trace no longer available"). Stop calls `POST /api/runs/{id}/cancel`.
- Chats: rename and delete (alertdialog) on the chat page and on `/app/chats`; unknown chat shows the 404 page with focus on its heading; two-tab freshness via refetch on window focus.
- Sources (sheet from `+`, and `/app/sources`): Feeds / APIs / Documents tabs (arrow key navigation), grouped by bubble ("No bubble" last), status as icon plus word, enable/disable switch, edit (URL and API mapping read-only; the server cannot patch them), delete with alertdialog and focus return, add forms with inline validation, duplicate URL "Already added" with link, test button, document upload (real file input plus drag and drop, XHR progress bar with aria-valuenow, unsupported file and 413/415/422 messages).
- Settings (`/app/settings`): masked key rendered as `sk-••••a7f2` with an sr-only "key ending a7f2"; key source in words; Replace key (focus on input; Cancel returns focus to Replace); Clear key with confirmation; base URL and model with validation; Save; Test connection in a polite live region; background-effects switch.
- Dot background (home only): one canvas, one rAF loop that runs only while the pointer moves or dots ease back (150ms), paused when hidden or while a run streams, DPR capped at 2, column fade, peak brightness overlay0. Off under reduced motion and when the Settings toggle is off. Pure math in `dotMath.ts`.
- API client: `web/src/api/*` (client with readable errors and NetworkError, chats, runs, settings, sources, documents XHR, bubbles, graph). Shared contract types in `web/src/api/types.ts`.

## Files touched

- Created: 80 files under `web/` (excluding `web/src/trace/**`, `web/src/graph/**`, `node_modules` and `dist`; those two are Agent C's and generated).
- Created: `web/.gitignore` (node_modules, dist, tsbuildinfo). The root `.gitignore` was not modified.
- Created: this handoff file.
- Generated, not committed: `web/package-lock.json`, `web/dist/`.
- Nothing committed or pushed.

## How to run

```
cd web
npm install
npm run dev          # http://localhost:5173/app/ ; proxies /api to OMNISTREAM_API or 127.0.0.1:8000
npx vitest run --exclude "src/trace/**" --exclude "src/graph/**"   # my suites: 65 tests, all pass
npx vite build       # passes; writes web/dist (served by FastAPI under /app, Agent A)
npx tsc -b --noEmit  # my files are clean; see concerns for C's errors
```

Test results at handoff: 12 test files, 65 tests passing (my suites). Full `vitest run` also runs Agent C's suites, where `src/trace/model.test.ts` had one failing assertion during the run.

## API assumptions (Agent A must match these)

All paths are under `/api`. Shapes follow spec section 12 and the brief's contract. These are not yet implemented by the backend in this tree.

- `GET /api/chats` returns `Chat[]`. `POST /api/chats` takes `{title}` and returns `Chat`.
- `GET /api/chats/{id}` returns `{chat, messages}` (a new shape, not in the brief). Unknown id returns 404.
- `PATCH /api/chats/{id}` takes `{title}`. `DELETE /api/chats/{id}`.
- `POST /api/chats/{id}/messages` takes `{content, mode, bubble_ids?}` and returns `{run_id}`. The user message is expected to carry `run_id`; assistant messages are expected to carry `run_id` too.
- `GET /api/runs/{id}` returns `Run`; `GET /api/runs/{id}/steps` returns `Step[]`. 404 on either means "trace no longer available" in the UI.
- `POST /api/runs/{id}/cancel` returns `Run`.
- `GET /api/bubbles` returns the existing `Bubble` shape.
- `GET /api/sources`, `POST /api/sources` (SourceIn), `PATCH /api/sources/{id}`, `DELETE /api/sources/{id}` (not in the existing app, required by the spec).
- `POST /api/sources/test` (NOT in spec section 12): takes SourceIn and returns `{items: [{title, url}]}` without storing. The UI shows "not available on this server yet" on 404 or 405.
- `POST /api/documents` (multipart: `file`, `bubble_ids` as a comma list, `credibility`), returns `IngestResult[]`. 413, 415 and 422 are mapped to messages.
- `GET /api/settings/provider` returns `{key_set, key_hint, key_source, base_url, model}`. `PUT` takes `{api_key?, base_url, model}`. `DELETE /api/settings/provider/key`. `POST /api/settings/provider/test` returns `{ok: boolean, message: string}` (shape assumed).
- `GET /api/graph` is used by Agent C with `{bubble, limit, offset}`.

Gaps for Agent A:
- `SourceIn` has no `backfill_days`. The feed form sends it when the user sets a value (documented in `SourceCreateInput`).
- `Source` has no items-ingested count and no "backing off" status. The UI shows status from `ok | error | pending` and `enabled`, and does not show an items count.

## Rulings (where the spec was silent or marked [Your call])

1. The context-manager request in the system prompt was skipped: no context-manager agent is available in this environment, so the spec and brief were used directly.
2. Chat title is the first 60 characters of the first question, sent as `title` on create.
3. No bubble chosen means `bubble_ids` is omitted (search all bubbles). A chosen source contributes its bubbles. Deleted bubbles or sources show "(no longer exists)" and are not sent. If every selection is gone, sending is blocked.
4. Mode is remembered per chat in localStorage (`omnistream.chatMode.<id>`), and the last choice is the default for new chats (`omnistream.defaultMode`). Not stored on the server.
5. Retry re-sends the same question with the current mode and all bubbles (the original scope is not stored).
6. Answer text is plain text (no markdown rendering).
7. The rail is on `/app/chat/:id` only. It is open by default at 1024px and wider, and collapsed by default below that (toggle button). The Sources sheet is on the right edge, full screen below 768px.
8. The live stage announcement says "step n" with no total, because the total is not known while a run is in progress.
9. Suggestion chips fill the input; they do not send.
10. Sources are grouped under the first bubble they belong to that still exists. Documents with no bubble are shown as live.
11. Background-effects toggle is stored in localStorage (`omnistream.backgroundEffects`), not SQLite.
12. The offline message is shown in the composer only (the spec puts it in the input). The shell has no separate banner.
13. Delete chat navigates to home and focuses the home heading.
14. Run progress uses polling (1.2s) instead of the SSE stream, to keep the chat independent of Agent C's trace code. Agent C's `stream.ts` could replace the polling later.
15. The test-source call is made with the same body as create. If the endpoint is missing, the button says so.
16. Document upload requires at least one bubble. Client-side extension check for `.pdf`, `.docx`, `.txt`, `.md`.
17. Poll interval options: 15 minutes, 1 hour, 6 hours, 1 day. Credibility defaults to 0.5, range 0 to 1.

## Integration with Agent C

- `web/src/router.tsx` imports `TracePage` from `@/trace` and `GraphPage` from `@/graph`, lazily. My placeholders were removed.
- Trace and graph import my `api/client.ts`, `api/runs.ts`, `api/graph.ts`, `api/types.ts` and `hooks/useMediaQuery.ts`. Their call signatures match what I export.
- Route params: `/app/trace/:runId` (C reads `useParams().runId`) and `/app/graph`.

## Concerns

1. `npm run build` runs `tsc -b` first and currently fails on Agent C's in-progress files: `src/graph/detail.ts` (unused `relevanceBand`), `src/trace/hooks.test.ts` (`live` option not in type), `src/trace/replay.test.ts` (`followTotal` not exported). `npx vite build` passes. My code typechecks clean.
2. Vitest: one assertion in Agent C's `src/trace/model.test.ts` failed in an earlier run ("expected 2 to be 1"). Not mine; left as is.
3. `npm audit` reports 6 high advisories for vite, vitest, picomatch, fdir, tinyglobby and @vitejs/plugin-react. These are dev tooling only and are not in `dist`. The audit's version data (vite 6.2.7, vitest 3.1.4) does not match the installed tree (vite 8.3.8, vitest 5.1.0). A non-breaking `npm audit fix` made no change; a forced fix would be a breaking change, so it was not applied.
4. Accessibility was verified by role, focus and keyboard tests (Testing Library), not by an automated audit (no axe in the dependencies). Contrast uses the spec's verified values; no contrast script was run. There was no 200% zoom or narrow-width visual check, and no screenshots were taken.
5. Dot-canvas performance budget (2 ms per frame at 1440x900) was not measured.
6. Visual layout was not checked in a browser beyond a production preview serving `/app/` assets and deep links.
7. The Markdown and rich text of answers are not rendered (plain text only).
8. `/api` backend endpoints listed above are not implemented in this tree yet, so the app cannot run end-to-end until Agent A lands.
