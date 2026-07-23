# HTTP Contract Changes — Feature 008

Existing endpoints keep their contracts unless listed. All routes stay
thin (Constitution IV); logic in engine/.

## Desktop shell support

| Route | Contract |
|---|---|
| `POST /api/open` | body `{url}`; scheme must be http/https else 400; calls host `webbrowser.open`; → `{opened: true}` |
| `POST /api/clipboard` | body `{text}`; host-side clipboard write; → `{copied: true}` or 500 `{detail}` (UI toasts either way) |

## Apply Assist (routes_autofill)

| Route | Change |
|---|---|
| `POST /api/autofill/setup` | **REMOVED** (no browser download). Returns 410 with migration hint for one release. |
| `POST /api/autofill/preflight` | NEW → `{ok, channel: "msedge"\|"chrome"\|null, error: str\|null}`; launches+closes a probe context |
| `POST /api/autofill/queue` | unchanged body; now runs preflight first — on failure 409 `{detail: reason + fix hint}` and queue does NOT start |
| `GET /api/autofill/status` | `chromium_installed` dropped; adds `browser: {ok, channel, error}`; `fell_back` → per-job `outcomes[{job_id, reason, detail}]`; rest of 007 payload unchanged |

## Feed / jobs (routes_api)

| Route | Change |
|---|---|
| `GET /api/jobs` + page routes | `window` gains `14d` (new default); new params `source=<name>`, `page=N` (maps to offset); `sort` unchanged; `entry_level=0` now means False; responses add `delisted`, `posted_approx` per job and `page`, `pages` totals |
| `GET /api/jobs/{id}/linkedin-url` | NEW → `{url}` LinkedIn search link-out for the job's title/terms (UI opens via /api/open) |

## Watchlist

| Route | Contract |
|---|---|
| `GET /api/watchlist` | → `{companies: [{id, ats, slug, name, enabled, origin}]}` |
| `POST /api/watchlist` | `{ats, slug, name?}` → 201 row; 409 on duplicate; validates ats value |
| `PATCH /api/watchlist/{id}` | `{enabled}` toggle |
| `DELETE /api/watchlist/{id}` | user rows deleted; shipped rows get `enabled=0` instead |

## Profile

| Route | Change |
|---|---|
| `POST /api/profile` (resume upload) | response/redirect adds `identity_conflicts: [{field, current, extracted}]` when extraction disagrees with non-blank user values; blanks are filled silently |
| `POST /api/profile/identity-conflicts` | NEW `{decisions: {field: "keep"\|"replace"}}` applies consent |
| `PUT /api/profile/search-terms` | NEW `{terms: [≤8 strings]}` → validated, stamped `derived_from: "user"` |
| `POST /api/profile/reextract` | also refreshes contact + target_titles + search_terms (same consent rules) |

## Updates

| Route | Contract |
|---|---|
| `POST /api/settings/check-update` | now returns/renders `{latest, newer, asset_url, size, sha256}` (platform asset selected server-side) |
| `POST /api/updates/download` | starts background download → `{started}` ; 409 if already downloading |
| `GET /api/updates/progress` | `{state: idle\|downloading\|verifying\|ready\|failed\|blocked, pct, error}` |
| `POST /api/updates/install` | only valid in `ready` (digest verified); hands off to installer and shuts the app down → `{installing: true}` |

## Diagnostics / What's New

| Route | Contract |
|---|---|
| `GET /diagnostics` (page) + `GET /api/diagnostics/all` | runs pdf / local-llm / browser-launch / embeddings / source-reachability checks → `[{name, ok, error, ms}]` (real error text, per audit finding) |
| `GET /api/diagnostics/logs` | zips app.log (+crash marker) to a download |
| `POST /api/diagnostics/cleanup-legacy-browser` | deletes legacy `browsers/` dir → `{freed_bytes}` |
| `GET /partials/whats-new` | returns the overlay when `WHATS_NEW_SEEN_VERSION != APP_VERSION`; `POST /api/whats-new/dismiss` stamps it |
