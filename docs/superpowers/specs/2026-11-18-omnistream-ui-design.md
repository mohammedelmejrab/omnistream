# OmniStream UI — Design Spec

Status: approved by the user (2026-11-18); both design reviews applied; contrast checked; next is the implementation plan
Scope: a project-sized UI (full written design)

Items marked **[Your call]** were decided by the author of this spec, not stated by the user. Everything else was confirmed by the user.

---

## 1. Intent and why

OmniStream ingests RSS feeds, APIs and documents into bubbles (one knowledge graph per domain) and answers questions with cited, merged answers. Today the only UI is a server-rendered admin area (`/ui/sources`, `/ui/unsorted`, `/ui/bubbles`, `/ui/ask`, `/ui/eval`), plus the JSON `POST /query` API.

The new UI should:

1. Let a user **ask questions** in a chat window that feels like Gemini's start screen.
2. Let the user **choose how the answer is produced**: **Normal** (own retrieval, single pass) or **Agentic** (orchestrator plus per-bubble subagents).
3. Let the user **build the knowledge base** from one menu: add RSS feeds, APIs and documents, which feed the graph.
4. Let the user **configure the model provider** (API key and OpenAI-compatible endpoint).
5. Make the system **traceable**: the user can watch the graph work live and replay any past answer.

Traceability is the main reason for this UI. A plain answer box is not enough; the user must be able to follow the path from source to answer.

## 2. Goals, non-goals, anti-goals

**Goals (v1)**
- Chat-first home screen with one input bar and a mode selector.
- Mode selector with two modes: **Normal** and **Agentic**.
- Animated starfield on the home screen: twinkling stars, shooting stars, and stars that bend around the cursor.
- A sources menu that adds RSS feeds, APIs and documents to bubbles.
- A settings page for the API key and OpenAI-compatible endpoint.
- A trace view that opens on a simple four-stage view, with the full graph available, live and after the fact.
- Chats persist and appear under "Recent".
- Catppuccin Mocha theme with rounded corners throughout.
- Designed for laptop screens first; layout adapts to screen size.

**Non-goals (v1)**
- Phone layout (v2).
- Voice input and the mic button.
- Answer rating (v3).
- Multi-user accounts, login, sharing, or permissions.
- Light theme.
- Multiple saved providers (v2; v1 has one active provider).
- Editing graph nodes or edges by hand.
- Changing the existing admin pages (`/ui/...`).

**Anti-goals** (failure even if it technically works)
- An answer with no visible way to see where it came from.
- A trace that only shows the final result, not the steps.
- A background animation that slows typing or drops frames on a mid-range laptop.
- The API key shown back in the browser after it is saved.
- Trace or graph detail that a non-expert cannot read by default.

## 3. Constraints

- Backend: FastAPI, SQLite via `Repository`, Neo4j / Graphiti for graph mode, the own algorithm in `retrieval/own_algorithm/`.
- The new UI is a React + TypeScript app built with Vite. This supersedes the earlier "no build step" rule in `src/omnistream/ui/README.md`, which still applies to the existing admin pages, and those are not changed.
- Single user, same origin: the React app and API are served by FastAPI, so no CORS setup is needed in production. In development, the Vite proxy forwards `/api` to FastAPI.
- Secrets: the API key is write-only. Pages never render `LLM_API_KEY` or api_mapping header values (existing rule; keep it).
- Accessibility: WCAG 2.2 AA. Keyboard-operable, visible focus, respects `prefers-reduced-motion`, works at 200% zoom.
- Theme: Catppuccin Mocha only (dark). Source: https://github.com/catppuccin/catppuccin

## 4. Approach

**Chosen: React + TypeScript + Vite single-page app, served by FastAPI, talking to a JSON API.**
- Why: the user chose React. Client state (live trace, chat list, settings) and graph/animation components are easier in React than in server-rendered HTML.
- Trade-off accepted: adds a Node toolchain and a build step for the new UI; two halves (Python API, TS front end) to keep in sync.
- Serving: the built app is served by FastAPI under `/app`. In development, the Vite dev server proxies `/api` to FastAPI. **[Your call]**

Rejected: extending the HTMX app.

## 5. Information architecture

```
/app                  Chat home. Opens on "Where should we start?" when empty.
/app/chat/{id}        A conversation, with answers and trace buttons. Unknown id → 404 page.
/app/chats            Full list of all chats ("See all").
/app/sources          Sources menu: feeds, APIs, documents, grouped by bubble.
/app/graph            Global graph viewer, filterable by bubble.
/app/trace/{run_id}   Trace of one run. Simple view by default; ?view=advanced opens the graph.
/app/settings         Provider: API key, endpoint, model; background-effects toggle.
/ui/...               Existing admin pages, unchanged.
/query                Existing JSON query API, unchanged.
```
**[Your call]** on the `/app` prefix.

**Every route** has its own page title, a skip link to the main content, and moves focus to the main heading on route change (WCAG 2.4.2).

## 6. Screen 1 — Chat home

Reference: a dark gradient background, the heading "Where should we start?", and a rounded input bar with a `+` button on the left, a placeholder, and the mode selector on the right.

```
╭───────────────────────────────────────────────────────────╮
│                  ·  ·  ·  ·  ·  ·  ·  ·                   │  starfield
│              ·  ·  ·  ·  ·  ·  ·  ·  ·  ·                 │  (reacts to cursor)
│                                                           │
│                Where should we start?                     │
│                                                           │
│  ( +  Ask OmniStream, or type @ for bubbles and sources ) │
│                                 [ ● Normal ▾ ]   [ ↑ ]    │
│                                                           │
│   Suggestions:  ( EU energy policy ) ( Bubble health )    │
│   Recent:       ( EU energy policy ) ( Tax changes ) ( See all ) │
╰───────────────────────────────────────────────────────────╯
```

**Layout**
- The input column is about 720px wide, centred.
- The heading sits about a third of the way down the page, with about 24px between it and the bar.
- Home shows up to three suggestion chips and up to three Recent chips under the bar, with a "See all" chip that opens `/app/chats`. The whole Recent row is hidden when there are no chats. **[Your call]** on suggestion content.
- Home has no side rail; the rail appears only on chat pages (section 11.2).

**Input bar**
- Pill-shaped while it is one line; switches to a 20px radius once the text wraps.
- `+` opens the **Sources menu** (section 8) as a panel.
- Placeholder: "Ask OmniStream, or type @ for bubbles and sources". **[Your call]**
- `@` opens an autocomplete of bubbles and sources (ARIA combobox pattern); selected items restrict the question to those bubbles. A bubble deleted after being typed is shown as "no longer exists" and is not sent. **[Your call]**
- Enter sends; Shift+Enter inserts a newline. The field grows to 6 lines, then scrolls.
- Question length limit: 20,000 characters, matching the existing `POST /query` limit. The counter appears near the limit.
- Send is disabled while empty, over the limit, or while a run is in progress. Disabled state uses a surface1 fill with overlay2 text.
- Offline: the bar shows "You're offline" and sending is disabled until the connection returns.

**Mode selector** (section 7): a pill-shaped menu button inside the input bar, right side.

**Heading**: "Where should we start?" shows only on an empty chat. Focus moves from the home input into the chat when the first message is sent.

**Browser Back** returns to the previous route, and the Back button leaves the chat without cancelling its run.

## 7. Mode selector — Normal and Agentic

A menu button (pill, shows the current mode) that opens a radio group with two options. Each option shows its description inside the open menu. The menu button has `aria-describedby` pointing at the current mode's description.

| Mode | Shape and colour | What runs | When to use | Trace shows |
|---|---|---|---|---|
| **Normal** | Circle, Blue | The own retrieval (`retrieval/own_algorithm/`), a single pass over the selected bubbles. | Fast, predictable answers | Picked bubbles → Gathered evidence (one total) → Wrote answer |
| **Agentic** | Diamond, Mauve | The orchestrator (`agents/orchestrator.py`) routes to bubbles, one subagent per bubble (`agents/subagent.py`) runs in parallel using the same own retrieval, then the orchestrator joins global entities and merges. | Multi-domain or open-ended questions | Picked bubbles → each bubble's work → Joined evidence → Wrote answer |

- The UI label is "Normal" and maps to the own algorithm (the internal name is unchanged).
- Each mode is a shape plus its colour plus its word. Colour is never the only cue.
- The choice is remembered per chat, and is the default for new chats in the browser. **[Your call]**
- Each answer records the mode it used; the answer header shows the mode badge.

## 8. Sources menu — feeds, APIs, documents

Opened from `+` or from `/app/sources`. Adds items to bubbles. Creating or editing bubbles stays on the existing `/ui/bubbles` page.

**Three source types**
- **RSS feed**: URL, bubble(s), poll interval, credibility (0–1, default 0.5), backfill days, full-text toggle. Matches the existing `SourceIn` model.
- **API**: URL, bubble(s), API mapping (how response fields map to items), headers (names shown, values never displayed), poll interval, rate limit. Matches `ApiMapping`.
- **Document**: upload of `.pdf`, `.docx`, `.txt` or `.md` (the formats `sources/documents.py` accepts), bubble(s). Uses the existing `POST /documents` endpoint.
  - The file can be chosen with the keyboard (a real file input) or by drag-and-drop, which always has the button alternative.
  - Upload progress is a progress bar with `aria-valuenow`.
  - Parse status is shown afterward. Clear messages for unsupported file, size limit and parse failure.

**Common behaviour**
- Each source shows: status (ok / backing off / error, with an icon and a word), last poll, items ingested, last error text.
- Enable/disable toggle.
- Delete asks for confirmation in an `alertdialog`; focus returns to the trigger afterward.
- A "test" button fetches once and shows the first items it would ingest, without storing them. The result is announced in a live region. **[Your call]**
- Adding a source never blocks the chat; ingestion runs in the background.
- Adding a source that duplicates an existing URL shows "Already added" with a link to the existing source.
- An invalid URL is rejected with an inline message before submit.
- A source whose bubble is deleted is marked "no bubble" and does not poll.
- If a source is being edited while its poll runs, the edit form keeps the user's values and shows "updated in the background" on save.
- If there are no bubbles or no sources yet, the menu says so and offers to add one.

**Layout:** a side sheet on laptop screens with square corners on the viewport-touching edge and 20px rounding on the inner side (exception to "rounded corners throughout", decision 29); full screen on narrow windows. Tabs: Feeds · APIs · Documents.

## 9. Settings

A page at `/app/settings`, reachable from the account/menu area.

- **Provider**
  - **API key**: write-only. Once saved, the UI shows a masked value, read by screen readers as "key ending a7f2" (for example `sk-••••a7f2`). The key is never returned to the browser.
  - **Replace key** is an explicit action. It opens an input with focus on it; Cancel returns focus to the Replace button.
  - **Clear key** removes the saved key (with confirmation).
  - The page shows which key is active: "Saved in OmniStream" or "From environment (LLM_API_KEY)".
  - **Base URL**: an OpenAI-compatible endpoint.
  - **Model name**: the model to call at that endpoint. An unknown model name is reported by Test connection.
  - **Test connection**: a loading state, then the result in a live region (success, or the error).
  - Save shows a confirmation. One active provider in v1; several saved providers in v2.
  - Storage: the existing SQLite `settings` table. The `LLM_API_KEY` environment variable is the fallback when nothing is saved in the UI.
- **Display**
  - **Background effects** toggle: turns the home-screen starfield off. The starfield ignores the device's reduced-motion setting, so this toggle is the way to stop it.
- If no key is configured, the home screen says so and links to Settings.

## 10. Trace view and storage

This is the traceability requirement.

### 10.1 What is traced

Each answer produces a **run** with an id and an ordered list of **steps**. Every step records:
- `id`, `run_id`, `parent_step_id` (tree shape), `kind` (route, seed, retrieve, score, subagent, join, merge, answer),
- `bubble` (where applicable), `started_at`, `duration_ms`,
- `status`: running / ok / error / cancelled,
- inputs and outputs summarised (ids, scores, counts), and the node/edge ids in the graph it touched,
- citations: item ids and source URLs used,
- `error` text, when status is error.

Each run also has an overall status: running / ok / failed / cancelled / interrupted.

Storage: new `runs` and `run_steps` tables, written as steps finish. Retention: 30 days. The existing `query_log` table is left untouched.

### 10.2 Simple view (default)

Opens by default with four plain-language stages:

1. **Understood your question**
2. **Searched bubbles** (shows which bubbles, as chips)
3. **Gathered evidence** (Normal: one total; Agentic: each bubble's result)
4. **Wrote answer** (shows the cited sources as numbered chips)

- Each stage shows a status icon and a word (done / working / could not finish / no evidence), not colour alone.
- **Replay works here too**: play, pause, step back, step forward and speed controls, and the four stages highlight in turn as the replay moves through them. A timeline strip shows each stage's duration.
- Relevance scores are shown as Low / Medium / High, with the number on hover and in the detail text.
- A failed bubble shows plain text, for example "Energy bubble could not answer", and the rest of the run still shows.
- If no relevant sources were found, stage 3 says "No relevant sources" and the answer says so plainly.
- The answer text sits beside or above the stages so the path from answer to source is visible without scrolling.
- Advanced is one toggle away; the choice is remembered per browser and is also available as `?view=advanced`.

### 10.3 Full graph (Advanced)

Opened with the "Advanced" toggle or `?view=advanced`.

- Nodes: the question, bubbles, subagents, entities and chunks touched, cited items, the final answer.
- Entities and chunks collapse into one count per bubble, expandable on click.
- Layout: deterministic left-to-right layered (dagre-style), so live and replay views match.
- Nodes appear as the run progresses; the active node pulses. The pulse stops after three cycles, and it is static under reduced motion. Replay can be paused (WCAG 2.2.2).
- Click a node: a 360px detail panel opens on the right with inputs, outputs, scores, and the source text it came from. On narrow windows the panel overlays the graph and never covers the focused node (WCAG 2.4.11). Focus moves to the panel; Esc closes it and returns focus.
- Click a cited item: jumps to the item and its source URL.
- A path highlight from the answer back to cited sources; everything else dims, but dimmed nodes keep at least 3:1 non-text contrast.
- Zoom and fit controls (+, −, fit) are buttons, so every pan and zoom has a non-drag alternative (WCAG 2.5.7). Node targets are at least 24×24px.
- A 120px timeline strip at the bottom shows each step as a bar with a 4px minimum width.
- Internal step names (route, seed, retrieve, score, join, merge) appear in the detail panel; the graph uses friendly labels.

**Library**: Cytoscape.js, used through a React wrapper. **[Your call]**

**Keyboard and screen readers**
- The canvas is not focusable on its own. A parallel DOM list of nodes sits beside it and is the keyboard path: arrow keys move through the list, and Enter opens the detail panel. The list and the graph read the same data.
- The simple view's stages and the list carry the same information as the graph.

### 10.4 Live, replay, and recovery

- During a run: the trace streams over Server-Sent Events (`GET /api/runs/{run_id}/events`). An `aria-live="polite"` region announces each stage in words, for example "Searching Energy bubble, step 3 of 6", not every event. Failures use `role="alert"`.
- If the connection drops, the client reconnects and fetches stored steps to catch up.
- After a run: `/app/trace/{run_id}` replays the same view from stored steps.
- Opening a trace for a run still in progress shows it live.
- **Failed runs:** completed steps stay saved and visible; the failed step is marked with its error; the chat shows the failure, not a blank answer.
- **Cancelled runs:** steps finished before cancel are kept; the run is marked cancelled.
- **Interrupted runs:** on server start, any run still marked running is set to interrupted (a stale-run sweep). Its steps are kept and the chat says "Interrupted when OmniStream restarted".
- **Deleted chat during a live run:** the run is cancelled and its steps are kept as an orphan trace reachable from the trace URL.
- **Two tabs on one chat:** messages are stored, so the second tab shows new messages on focus or on the next reload; a run started in one tab appears in the other as it streams.
- **Expired traces** (after 30 days): the chat keeps the answer and shows "Trace no longer available".

### 10.5 Global graph viewer (`/app/graph`)

- Shows the whole graph by bubble, filterable by bubble and source.
- Read-only. Search by entity name. Node counts per bubble.
- Uses the same parallel DOM list and zoom/fit buttons as the Advanced trace.
- Large graphs show up to 300 nodes per view, with a "load more" control for the rest.
- An empty graph shows an empty state that links to Sources.

### 10.6 Chats

- New tables: `chats` and `messages`. Chats persist across reloads and appear under "Recent" and on `/app/chats`.
- Chats can be renamed and deleted. Delete asks for confirmation in an `alertdialog`.
- With no chats, the Recent row is hidden on home and `/app/chats` shows an empty state.
- Each assistant message links to its run.

## 11. Look and feel — Catppuccin Mocha

**Colour tokens**
- Background: Mocha **base**. Depth: **mantle** and **crust**. Cards and the input bar: **surface0**; hover and selected states: **surface1**.
- Primary actions and focus: **Lavender** (`#b4befe`). Lavender fills carry **crust** text (10.5:1). Focus ring is 2px Lavender with a 2px offset (9.2:1 on base, 7.0:1 on surface0).
- **Normal** mode: **Blue**, circle marker. **Agentic** mode: **Mauve**, diamond marker.
- Healthy / ok: **Green**. Warning: **Peach**. Error: **Red**. Each status has an icon and a word as well as colour.
- Body text: **text** (11.3:1 on base). Secondary text and placeholders: **subtext0** (7.4:1 on base, 5.7:1 on surface0).
- Disabled controls: surface1 fill with overlay2 text. Disabled controls are exempt from the contrast requirement under WCAG.
- Decorative only, exempt from text rules: the starfield (Mocha overlay0, subtext0, text, lavender, blue, mauve and sapphire tints only) and its soft glow.

**Verified contrast (WCAG 2.2 relative luminance)**

| Pair | Ratio | Use |
|---|---|---|
| text on base | 11.3 | Body text |
| subtext0 on base | 7.4 | Secondary text |
| subtext0 on surface0 | 5.7 | Placeholders on inputs |
| lavender on base | 9.2 | Focus, links |
| crust on lavender | 10.5 | Primary button text |
| blue on base | 7.8 | Normal marker and label |
| mauve on base | 8.1 | Agentic marker and label |
| green / peach / red on base | 11.0 / 9.3 / 7.1 | Status text |
| peach / red on surface0 | 7.1 / 5.4 | Status on cards |
| overlay2 on surface0 | 4.5 | Not used for text (too close to the 4.5 minimum) |
| overlay0 on base | 3.4 | Not used for text |

**Radius scale (design tokens)**

| Token | Value | Applies to |
|---|---|---|
| `r-xs` | 4px | Timeline bars, small badges |
| `r-sm` | 8px | Buttons (non-pill), text fields, menu items, graph node rectangles |
| `r-md` | 12px | Cards, dropdowns, source rows, the detail panel (also when it overlays on narrow windows) |
| `r-lg` | 20px | Side sheets (inner edge), large containers, answer blocks, multi-line input bar |
| `r-pill` | 9999px | Single-line input bar, mode menu button, suggestion and Recent chips, "See all", filter chips, toggles, status chips |

Rules:
- Answer blocks use `r-lg` because they are large containers; cards and list rows use `r-md`.
- Nested elements use inner radius = outer radius minus padding.
- Side sheets are square on the edge touching the viewport, the one exception to rounded corners throughout (decision 29).
- Graph nodes are circles or `r-sm` rectangles (not pills), so long names can truncate cleanly.
- The starfield canvas is full-viewport and is not rounded.

**Focus and states**
- Every interactive element has a visible focus ring (Lavender) and a minimum 24×24px target; Send is 44px.
- Reduced motion disables the node pulse, replay animation and panel transitions.

### 11.1 Responsive layout

- Designed for laptop screens first (around 1280–1440 px wide).
- The layout adapts to screen size: side rails collapse on narrower windows; the trace detail panel overlays the graph instead of sitting beside it; the trace graph reflows.
- Narrow windows must not break or scroll horizontally, and layouts hold at 200% zoom. Phone-specific design is v2.
- Breakpoints:
  - 1280px and up: full layout (the design target).
  - Below 1280px: at 1024px the Recent rail collapses and the trace detail panel overlays the graph.
  - Below 768px: side sheets become full-screen.
  - Below 768px the layout must not break; phone design is v2.

### 11.2 Chat and rail

- Chat pages show a collapsible 260px "Recent" rail on the left. It collapses on narrower windows. Home has no rail.
- Landmarks: `nav` for Recent, `main` for the conversation.

### 11.3 Starfield background

- **Home screen only.** Other pages use a plain mantle background.
- A full-viewport canvas of stars in three depth layers: 520 small dim far stars, 220 mid stars, and 70 larger near stars. Positions are fractions of the viewport from a fixed seed, so the layout does not reshuffle on resize.
- Stars twinkle quickly: about 0.5 to 1.8 Hz, within ±45% of their brightness. Six of the near stars carry a soft glow.
- Cursor swirl: stars within 110px of the pointer revolve slowly around it (up to about 1.3 rad/s at the pointer, slower further out) and are nudged outward up to 22px. Each orbiting star leaves a short arc-shaped trail. The fade behind the text column is lifted near the pointer so the swirl shows over the column. Stars inside the lens brighten and grow. Outside the lens, stars settle back to their home spot.
- The warp holds while the pointer is inside the page and has moved within the last 1.5 s. It eases back over about 200ms when the pointer leaves the page or goes idle for 1.5 s.
- Shooting stars: every 4 to 9 seconds (random) one streaks down and to the right with a fading tail, lasting 0.8 to 1.2 seconds. Angle is 18 to 45 degrees and length 160 to 400px, so shots vary. At most one is on screen at a time.
- The field fades out behind the central text column so the heading and input stay readable. No star is brighter than Mocha text. Stars are decorative and exempt from text contrast.
- Implementation: one `<canvas>` and one `requestAnimationFrame` loop. The loop runs while the home screen is visible and not paused, and it stops while a run streams and when the tab is hidden. This replaces the earlier "loop only while the pointer moves": twinkle and shooting stars need continuous frames. `devicePixelRatio` capped at 2. The canvas is `aria-hidden` and not focusable.
- Motion setting: the starfield always animates, whatever the device's reduced-motion setting (decision by the user, 2026-11-18). The Settings "Background effects" toggle is the way to switch it off. Other motion (node pulse, replay animation, panel transitions) still follows reduced motion.
- Off when the Settings toggle is off (nothing is rendered).
- Performance budget: under 2 ms per frame at 1440×900 on a mid-range laptop. **[Your call]**

## 12. API surface (new, additive)

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/chats` | Create a chat. |
| GET | `/api/chats` | List chats for "Recent" and `/app/chats`. |
| GET | `/api/chats/{id}` | A chat and its messages. Unknown id → 404. |
| PATCH | `/api/chats/{id}` | Rename a chat. |
| DELETE | `/api/chats/{id}` | Delete a chat. |
| POST | `/api/chats/{id}/messages` | Send a question with `mode` (`normal` \| `agentic`) and optional `bubble_ids`. Returns `run_id`. |
| POST | `/api/runs/{run_id}/cancel` | Cancel a running run. |
| GET | `/api/runs/{run_id}` | Run summary and final answer. |
| GET | `/api/runs/{run_id}/events` | SSE stream of step events. |
| GET | `/api/runs/{run_id}/steps` | Stored steps (for replay). |
| GET/PUT | `/api/settings/provider` | Read the provider (key masked, and which source is active) and save key, base URL, model. |
| DELETE | `/api/settings/provider/key` | Clear the saved key. |
| POST | `/api/settings/provider/test` | Test the connection. |
| GET/POST/PATCH/DELETE | `/api/sources...` | Reuse existing source endpoints. Documents use `POST /documents`. |
| GET | `/api/graph?bubble=...` | Nodes and edges for the global viewer. |

Unchanged: `POST /query` and the `/ui/...` admin pages.

## 13. States and errors

- Empty chat: heading, suggestions, and the Recent row hidden.
- No provider key: home says so and links to Settings; sending is disabled.
- No bubbles or sources: Normal and Agentic say there is nothing to search and link to Sources.
- No relevant sources found: stage 3 says "No relevant sources", and the answer says so rather than inventing one.
- Empty answer from the provider: shown as a failed run with "The model returned no answer" and a Retry action.
- Run in progress: input disabled with a Stop button; the trace shows the current stage.
- Cancelled run: partial steps kept; the chat shows "Stopped".
- Interrupted run (server restart): steps kept; the chat shows "Interrupted when OmniStream restarted".
- Subagent failure (Agentic): that bubble shows "could not answer"; the answer still merges the others and says which bubble failed.
- Provider failure (bad key, wrong URL, rate limit, invalid model name): the run ends as failed with a readable message; no secrets shown.
- Offline: the input shows "You're offline" and sending is disabled; the app resumes when the connection returns.
- Source errors: shown in the Sources menu with the last error; the chat keeps working.
- Upload errors: unsupported file, over the size limit, or parse failed, each with its own message.
- Duplicate or invalid source URL: inline messages (section 8).
- Expired trace: "Trace no longer available".
- SSE disconnect: automatic reconnect with catch-up.
- 404 (unknown chat or run) and server-down: a simple page with a link back to Chat, and focus on the heading.

## 14. Testing

- Unit: step recording (order, parent links, durations, error, cancelled and interrupted status); mode routing (Normal calls the own pipeline once; Agentic calls the orchestrator); question length limit; stale-run sweep marks running runs as interrupted on start.
- API: SSE event order; replay from `/api/runs/{id}/steps` matches live events; cancel stops a run; delete during a live run cancels it; the key is never returned; unknown chat returns 404.
- UI: keyboard path (focus to `+`, mode menu, send, the parallel node list with arrow keys and Enter, panel Esc); graph zoom and fit buttons work without dragging; reduced-motion path; no horizontal scroll at narrow widths and at 200% zoom; screen-reader announcements for live stages; page title and focus on route change; Back button behaviour.
- Visual: screenshots of home and trace in Mocha, compared to the reference layout; contrast check on every token pair (values in section 11 are already verified).

## 15. Decisions log

Confirmed by the user:

| # | Decision |
|---|---|
| 1 | Frontend: React + TypeScript + Vite, served by FastAPI. |
| 2 | Every run is recorded, kept 30 days, and streamed live. |
| 3 | Single user, no auth. Settings for API key and OpenAI-compatible endpoint. |
| 4 | Chats persist and appear under "Recent". |
| 5 | The `+` menu adds sources to existing bubbles only. |
| 6 | Mic button removed from v1. |
| 7 | Catppuccin Mocha theme. |
| 8 | Build order: working chat → answer → trace loop first, polish second. |
| 9 | Laptop first; phone layout in v2. |
| 10 | New `runs`, `run_steps` tables; `query_log` untouched. |
| 11 | New `chats` and `messages` tables. |
| 12 | Live trace streamed over SSE in v1. |
| 13 | Agentic = orchestrator + subagents, both using own retrieval. Normal = own, single pass. |
| 14 | Existing `/query` and `/ui/...` endpoints unchanged. |
| 15 | Answer rating moved to v3. |
| 16 | React + TypeScript + Vite; admin pages unchanged. |
| 17 | API key stored in SQLite `settings`, write-only and masked; env var as fallback. |
| 18 | One active provider in v1; multiple providers in v2. |
| 19 | Mocha colour mapping as in section 11. |
| 20 | Layout adapts to screen size; rounded corners throughout. |
| 21 | Failed runs keep partial traces and show the failure. |
| 22 | Primary actions and focus in Lavender; Mauve for Agentic only. |
| 23 | Trace opens on a simple four-stage view; full graph behind "Advanced". |
| 24 | Starfield (with a cursor swirl and trail, and shooting stars) on the home screen only, with a Settings toggle. Always animated, regardless of the device's reduced-motion setting. |
| 25 | Input column about 720px centred; Recent rail 260px and collapsible on chat pages. |
| 26 | Mode selector is a menu button with a radio group; descriptions shown inside the menu. |
| 27 | Replay controls and the timeline also work in the simple view; stages highlight during replay. |
| 28 | Older chats reached through a "See all" chip that opens `/app/chats`. |
| 29 | Side sheets keep square corners on the viewport edge (exception to rounded corners throughout). |
| 30 | Normal is a circle marker and Agentic a diamond marker, so the modes differ by shape as well as colour. |
| 31 | Breakpoints at 1280px (full layout), 1024px (rail collapses, trace panel overlays), 768px (sheets full-screen). |
| 32 | The global graph viewer shows up to 300 nodes per view, with "load more". |

Facts found in the repo:
- Document formats accepted: `.pdf`, `.docx`, `.txt`, `.md` (`sources/documents.py`). Upload exists at `POST /documents`.
- No streaming/SSE code exists yet; no run or step concept exists yet.
- `query_log` table exists but nothing writes to it.
- There is no `/ask` route; the JSON API is `POST /query` (limit 20,000 characters), and the HTML page is `/ui/ask`.
- No chat or conversation table exists yet.

## 16. What is left to the builder

- Responsive behaviour details within the breakpoints in section 11.1.
- Star layout, warp radius and falloff, and shooting-star timing.
- Graph layout algorithm and node styling.
- Component file layout for the React app.
- Suggestion chip content on the home screen.

## 17. Next steps

1. Apply any final changes you request.
2. Implementation plan (superpowers:writing-plans). Nothing is built before you approve the spec.
