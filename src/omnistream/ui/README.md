# UI

Server-rendered Jinja2 pages (`/ui/sources`, `/ui/unsorted`) with HTMX.
`static/htmx.min.js` is vendored (htmx 2.0.4, from unpkg); there is no build step.
Pages never render `LLM_API_KEY` or api_mapping header values (names only).
