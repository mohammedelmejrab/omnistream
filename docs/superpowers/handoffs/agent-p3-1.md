# Agent P3 handoff 1: visual polish (web/, round 3)
Status: DONE, with two concerns for the owner (see Concerns). All gates green.
Spec: docs/superpowers/specs/2026-11-18-omnistream-ui-design.md (sections 6-11, 14). Brief: round3-polish.md.
Skills: superpowers:test-driven-development (new behaviour tests written before the change), superpowers:verification-before-completion (every claim below from a command run this round). No frontend-design plugin was available in this session, so the design pass followed spec section 11 directly.
No commits, no pushes, no .gitignore changes, no Claude attribution.

## Verification gates (run from web/)
- `npx tsc -b --noEmit`: clean
- `npx vitest run`: 26 files, 206 tests, all pass (5 Timeline tests, 1 Settings test added this round)
- `npm run build`: clean (graph chunk still over 500 kB, as before)
- `npx playwright test`: 16 passed (server started by the config on 8765). Full gate run twice after the regression fix below; both runs green.

## What was done
1. **Timeline strip (simple and advanced).** Simple strip is 24px (advanced 56px; spec says "up to 120px", chosen smaller for a slim strip). Bars are sized by duration alone (`flex-grow` = ms), so a 0 ms step gets only the 4px minimum rather than a 1-unit share. Status colours are mixed into the surface at about 38% strength; failed uses red at 55%; the current bar gets a lavender outline. 2px gaps separate bars.
2. **Timeline tooltips.** Each bar carries `data-label` ("3 Gathered evidence: 18 ms") and `data-edge` (start or end half). The tooltip shows on hover and keyboard focus, anchored to the nearer edge, max 160px wide. Hidden tooltips are `display: none`, and the strip has `overflow-x: clip`.
   **Regression fixed (layout.spec.ts):** the round-3 tooltips were laid out while hidden (`opacity: 0`), which widened the page to 546px at 360px on `/app/trace/{id}?view=advanced`. Now 360px, and hovering a middle bar also stays at 360px.
3. **Legend.** The duration text list became a legend with a status swatch, number, name and duration. The stage names now appear twice on the simple view (card and legend); tests that match names inside the page were scoped to the stage list (`TracePage.test.tsx`).
4. **Advanced graph labels.** Node font 13 → 15, nodes 140×52 with two-line wrapping (was one ellipsised line), entities 13px, group nodes 236px. Rank gap 60 → 36 and node gap 18 → 16 so the graph uses the canvas width. Measured zoom at fit (rendered px ≈ 15 × zoom): 1440 → 15.2, 1280 → 12.8, 1024 → 13.1. Before: about 11.5 and 8.
5. **Fit cap.** `fitView()` in `GraphCanvas.tsx` caps the fit zoom at 1.3 and centres. A 4-node global graph no longer blows up to 2.5×.
6. **Edges.** overlay1, 1.25px, 85% opacity (was overlay0, 1.5px). Dimmed edges 60%.
7. **Detail panel open at 1280px and up.** The list now stacks under the graph (`:has(.detail-panel)` in `graph.css`), so the graph keeps its width. Without this the labels fell to 8–11px. The list keeps every item. Below 1280 the panel already overlays and the list stays where it was.
8. **Rail.** Recent rail collapses at 1024px and below (was below 1024). Spec 11.1 says "at 1024px the Recent rail collapses".
9. **Settings.** Masked key with no hint (environment key) reads `sk-••••••••` and "API key is set" for screen readers. Before: "sk-••••" with nothing after it and "key ending unknown" read aloud. Display toggle restyled as a 40×22 track with the label beside it (was a filled pill with the label inside). Test added (`SettingsPage.test.tsx`).
10. **Focus.** Route-change headings (`h1[tabindex=-1]`) no longer draw a lavender ring on focus. Controls keep their ring.
11. **Native file input.** "Choose File" takes the pill button style (`components.css`).
12. **Offline and sheet.** Checked, no change needed: offline notice on home with send disabled; the `+` sources sheet has square outer edge and rounded inner corners.

## Files touched
Source (web/src):
- `trace/Timeline.tsx` (flex-grow by duration, `data-label`), `trace/Timeline.test.tsx` (new, 5 tests)
- `trace/format.ts` (new: `formatDuration`, moved out of SimpleView to avoid an import cycle; SimpleView re-exports it)
- `trace/SimpleView.tsx` (legend replaces the duration list)
- `trace/trace.css` (timeline, tooltip, legend rules replaced)
- `trace/TracePage.test.tsx` (one query scoped to the stage list)
- `graph/cytoscape.ts` (font, node size, wrap, edges)
- `graph/model.ts` (rankSep 36, nodeSep 16)
- `graph/GraphCanvas.tsx` (`fitView`, `FIT_MAX_ZOOM`)
- `graph/graph.css` (stacked list with panel open at 1280px+)
- `layout/Rail.tsx` (NARROW breakpoint 1024px)
- `pages/SettingsPage.tsx` (`maskedKeyText`, `maskedKeyReading`), `pages/SettingsPage.test.tsx` (1 test)
- `theme/components.css` (switch, file input), `theme/global.css` (heading focus)
Generated (not committed): `web/dist/`, `web/e2e/screens/polish-*.png` (25 screenshots: all routes at 1440×900 and 1024×768, graph and trace panel states, offline, sources tabs and sheet, timeline hover).

## How to test
From web/: run the four gates above. For a visual check, start the e2e server (`../.venv/bin/python e2e/support/serve_e2e.py 8799`) and open `/app/trace/{run}?view=advanced` after asking a question.

## Rulings (where spec was silent or ambiguous)
1. **Body background stays mantle on non-home pages.** Spec 11.3 says "Other pages use a plain mantle background", so C3's concern 1 is not a defect. Home keeps its base gradient.
2. **Advanced timeline 56px, simple 24px.** Spec gives "120px" for the advanced strip; "up to 120px" in the brief allows a slimmer strip.
3. **Zero-duration steps get the 4px minimum only.** Keeps the strip proportional (the brief allows the 4px distortion only).
4. **Fit zoom capped at 1.3.** Keeps small graphs from filling the canvas with oversized nodes.
5. **With the detail panel open at 1280–1439px the list moves under the graph.** Spec 10.3 says the list sits "beside" the graph. Stacking is a deviation that keeps the graph readable; see Concerns.
6. **Rail collapse at exactly 1024px.** Read spec 11.1's "at 1024px" as inclusive.

## Concerns (for the owner)
1. **Layout decision (ruling 5).** Stacking the list under the graph when the panel is open departs from "list sits beside" in spec 10.3. Without it, labels are 8–11px at 1280–1440 with the panel open. The alternative is to accept smaller labels there (the list has the same information). Decide before final sign-off.
2. **Global graph labels (backend, unchanged from C3).** Two "Alice" and two "Acme" nodes look identical on `/app/graph`. A bubble name on each label or in its meta would fix it (frontend-only via `buildGlobalGraph`).
3. **Environment key has no hint (backend).** `GET /api/settings/provider` returns `key_hint: null` for `LLM_API_KEY`. The UI now masks it without an ending. Showing the last four characters of an env key would be a backend choice.
4. **Timeline bar dominance is the data.** In a real run the retrieval step can take most of the strip. The legend gives every number; this is not a bug.
5. **Not reviewed in this round:** a real no-key state (the e2e server always has a key), and the Settings "Test connection" result and error notices. Those need a server started without `LLM_API_KEY`.
6. **Carried from B2:** the two API path blockers (`/api/bubbles`, `/api/documents`), and `npm audit` (6 high, dev tooling only). Not touched.
7. **Generated screenshots.** `web/e2e/screens/` and `web/e2e/.results/` are untracked. Decide whether screenshots belong in the repo before commit.
