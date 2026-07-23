# Tasks: Launch Release (v0.8.0)

**Input**: spec.md, plan.md, research.md, data-model.md, contracts/http-api.md
**Workflow**: hybrid — every deterministic-logic task follows superpowers TDD
(write test → watch it FAIL → implement → green). Test tasks are listed
explicitly and MUST fail before their implementation task starts.

**Total**: 56 tasks — Setup 2 · Foundational 3 · US1 8 · US2 8 · US3 14 ·
US4 7 · US5 9 · US6 4 · Polish/Ship 1 (numbering is execution order).

## Phase 1: Setup

- [X] T001 Update dependencies: pin `pywebview>=6.2` in requirements.txt; verify installed playwright supports `channel=` persistent launch; add `assets/models/embeddinggemma-300m-q8_0.gguf` acquisition (documented download step + CI cache) and reference it from packaging notes
- [X] T002 [P] Add new settings defaults (`FEED_WINDOW_DEFAULT=14d`, `JOBSPY_SITES`, `JOBSPY_RESULTS_PER_SEARCH`, `LLM_JSON_MODEL`, `LLM_PROVIDER_PRESET`, `WHATS_NEW_SEEN_VERSION`, `UPDATE_LAST_CHECK`) in engine/settings.py

## Phase 2: Foundational (blocking all stories)

- [X] T003 [test] Failing tests in tests/test_db.py: migrations add `jobs.last_seen_at` (backfilled from first_seen), `jobs.delisted`, `jobs.embedding`, `user_profile.search_terms`, `user_profile.resume_embedding`, `watchlist` table; `init_db()` writes `backup/jobs-v{old}.db` before migrating and restores it on simulated migration failure
- [X] T004 Implement the migrations + backup-before-migrate/restore-on-failure in engine/db.py
- [X] T005 Watchlist seed: expand companies.yml to 300+ curated boards (CE/hardware/semis/defense + known sponsors; validate slugs via scripts/check_seeds.py) and implement one-time seeding into the `watchlist` table (engine/watchlist.py `ensure_seeded()`, re-seed inserts only unknown shipped slugs) with tests in tests/test_watchlist.py written first

## Phase 3: US1 — Apply Assist that works or explains (P1)

- [X] T006 [test] [US1] Failing tests in tests/test_browser_controller.py: `_ensure_context` launches via `channel="msedge"`, falls back to `"chrome"`, raises typed `BrowserUnavailable` with detail after both fail (playwright monkeypatched)
- [X] T007 [US1] Implement channel-based launch in engine/autofill/browser_controller.py (`user_data_dir=data_dir()/browser-profile`, no PLAYWRIGHT_BROWSERS_PATH); delete the download path from engine/autofill/browser_setup.py, leaving `legacy_browsers_dir_size()`/`cleanup_legacy()` helpers
- [X] T008 [test] [US1] Failing tests: `outcomes` dict replaces `fell_back` with reason classes `launch_failed|nav_failed|scan_failed|unrecognized|filled|manual|skipped` + detail text; `queue_snapshot()` exposes them; launch failure during a queue marks `launch_failed` (not generic manual)
- [X] T009 [US1] Implement reason-class outcomes in browser_controller (`_open_job`, `_fill_page`, `_job_outcome`, `queue_snapshot`)
- [X] T010 [test] [US1] Failing tests in tests/test_routes_autofill.py: `POST /api/autofill/preflight` returns `{ok, channel, error}`; `POST /api/autofill/queue` runs preflight and 409s with reason on failure; `POST /api/autofill/setup` returns 410; status payload has `browser` + `outcomes`, no `chromium_installed`
- [X] T011 [US1] Implement preflight + route changes in web/routes_autofill.py and engine/autofill/browser_controller.py `preflight()`
- [X] T012 [US1] Rebuild web/templates/autofill.html (remove download/setup flow; preflight card with error + retry) and web/templates/partials/autofill_status.html (distinct message per reason class, real error text)
- [X] T013 [US1] Packaging: assert playwright Node driver bundled in packaging/jobengine.spec; remove Chromium-install steps from CI smoke prep; smoke test asserts preflight endpoint answers (ok or typed error) in the frozen build

## Phase 4: US2 — A desktop window the user can trust (P2)

- [X] T014 [test] [US2] Failing tests in tests/test_api.py: `POST /api/open` (http/https only, 400 otherwise, calls webbrowser.open — monkeypatched), `POST /api/clipboard` writes via engine clipboard helper (monkeypatched) and 500s honestly
- [X] T015 [US2] Implement `/api/open` + `/api/clipboard` in web/routes_api.py with engine/clipboard.py helper (PowerShell Set-Clipboard / pbcopy / xclip fallbacks)
- [X] T016 [US2] desktop.py: `text_select=True`, `confirm_close=True`, `min_size=(960,640)`; `webview.settings["ALLOW_DOWNLOADS"]=True` and `["OPEN_EXTERNAL_LINKS_IN_BROWSER"]=True`; acquire `JobEngineRunning` mutex via ctypes (Windows); fix fatal-startup message to name app.log path
- [X] T017 [US2] web/static/app.js: `window.copyText(text)` (clipboard → execCommand fallback → /api/clipboard, always toasts) and delegated `a[target=_blank]` click handler posting to /api/open
- [X] T018 [US2] Replace the 3 inline `navigator.clipboard` handlers in web/templates/job_detail.html with `copyText(...)`; convert "Open posting" to the /api/open path (href kept as browser-mode fallback)
- [X] T019 [US2] Add Copy-link buttons: feed rows (web/templates/partials/feed_table.html actions cell) and job detail header; show raw URL on job detail
- [X] T020 [test] [US2] Template render tests: copy-link buttons present with correct URLs; no remaining inline `navigator.clipboard` usage anywhere in templates (grep-style test)
- [X] T021 [US2] Global error visibility: `sys.excepthook` + `threading.excepthook` → app.log + `crash.marker`; base template shows one-time "closed unexpectedly last time" notice when marker present

## Phase 5: US3 — Genuine, fresh, sortable feed (P3)

- [X] T022 [test] [US3] Failing tests in tests/test_db.py: `14d` window in query_jobs (and new default), `delisted=1` excluded from default views/included with flag in `all`, dedup_key hit suppresses same-source repost (URL refresh, no duplicate row), `last_seen_at` stamped on every upsert path
- [X] T023 [US3] Implement window/delist/dedup/last_seen changes in engine/db.py; default window threaded through web/routes_api.py parse_feed_params + web/main.py + feed.html segmented control ("2 weeks" default)
- [X] T024 [test] [US3] Failing tests in tests/test_pipeline.py (or test_ingest): delisting pass marks rows absent from a successful full-board fetch, never on failed/empty-error fetch; reappearing job restored; ingest-time 14-day age gate skips old date-bearing rows
- [X] T025 [US3] Implement board-diff delisting + ingest age gate in engine/pipeline.py and engine/ingest/(greenhouse|lever|ashby|workable).py (sources return full-fetch success flag + seen keys)
- [X] T026 [test] [US3] Failing tests: throttled HEAD liveness check for scraped-board rows (404 / redirect-to-careers-home ⇒ delisted; network error ⇒ no change), respecting 1 req/s/domain
- [X] T027 [US3] Implement liveness checker in engine/pipeline.py (bounded batch per refresh, scraped sources only)
- [X] T028 [US3] Watchlist runtime: pipeline.load_companies reads the watchlist table (enabled rows) instead of YAML; per-board "not found" surfaces in the refresh strip via `last_ok_at` (tests first in tests/test_watchlist.py)
- [X] T029 [test] [US3] Failing tests in tests/test_api.py: watchlist CRUD contract (GET/POST 201/409, PATCH enabled, DELETE user-vs-shipped semantics)
- [X] T030 [US3] Implement watchlist CRUD in web/routes_api.py + Settings watchlist section in web/templates/settings.html
- [X] T031 [US3] jobspy upgrades in engine/ingest/jobspy_source.py: sites from `JOBSPY_SITES` (+google; linkedin only when opt-in), `hours_old=336` passed alone (client-side job_type/remote filtering), results_wanted from settings; tests first (kwargs asserted via monkeypatched scrape)
- [X] T032 [US3] LinkedIn link-out: engine/ingest/linkedin_linkout.py builds search URLs (terms + f_TPR=r1209600); `GET /api/jobs/{id}/linkedin-url` + toolbar/job-detail "Search on LinkedIn" buttons (open via /api/open); LinkedIn checkbox copy updated with rate-limit warning
- [X] T033 [US3] Feed usability: sort auto-applies on change; segmented window/view links rebuilt from full query string; hidden seen/ineligible/view inputs in toolbar form; Prev/Next pager (total/limit/offset); `source` filter param + select in query_jobs/routes/template; fix `entry_level='0'`→False; clickable Posted/Match headers (template render + route tests first)
- [X] T034 [US3] Honest dates: `posted_approx` flag in job payloads; feed/detail show "seen {date} ~" styling for NULL posted_date rows; MAX_SCORE_PER_RUN scaled with volume knobs (settings-driven)
- [X] T035 [US3] Delisted badge styling + "delisted" filter chip in `all` window (web/static/styles.css + feed_table.html)

## Phase 6: US4 — Profile fills itself; search follows it (P4)

- [X] T036 [test] [US4] Failing tests in tests/test_resume_extract.py: `Contact`/`target_titles` submodels parse; regex fallback extracts email/phone/URLs from header lines with no AI tier; never returns fabricated values
- [X] T037 [US4] Implement contact + target_titles extraction (schema, _SYSTEM prompt, regex fallback) in engine/resume_extract.py
- [X] T038 [test] [US4] Failing tests in tests/test_api.py: resume upload fills only blank identity fields; conflicting non-blank fields returned as `identity_conflicts`; `POST /api/profile/identity-conflicts` applies keep/replace; visa/work-auth never auto-filled
- [X] T039 [US4] Implement identity auto-fill + consent flow in web/routes_api.py save_profile/reextract + conflict UI in web/templates/profile.html
- [X] T040 [test] [US4] Failing tests in tests/test_search_terms.py: derivation from target_titles/experience/skills capped at 8, stable ordering, empty-profile → []; PUT /profile/search-terms validates and stamps `derived_from:"user"`
- [X] T041 [US4] Implement engine/search_terms.py + persistence + `PUT /api/profile/search-terms` + editable terms UI on profile.html (with "these drive the job search" note)
- [X] T042 [US4] Consume profile in sourcing: jobspy terms×locations from profile (fallback to built-in constants), target_locations pre-fills the feed location filter as documented (web/main.py); tests first in tests/test_ingest*/test_api.py

## Phase 7: US5 — In-app updates, What's New, Diagnostics (P5)

- [X] T043 [test] [US5] Failing tests in tests/test_updates.py: platform asset selection from a releases-API fixture, semver compare, SHA-256 verify (reject mismatch/partial), download progress state machine (idle→downloading→verifying→ready/failed/blocked), install refused unless `ready`
- [X] T044 [US5] Implement engine/updates.py download/verify/install-handoff (`/VERYSILENT /SUPPRESSMSGBOXES /NORESTART /STARTAPP=1`, detached, app exit) + once-daily startup check throttle
- [X] T045 [US5] Routes + UI: `/api/updates/download|progress|install`, upgraded check-update response, update banner with progress bar in base/settings templates (web/routes_api.py, web/static/app.js)
- [X] T046 [US5] What's New: versioned changelog dict, `GET /partials/whats-new` overlay + dismiss endpoint stamping `WHATS_NEW_SEEN_VERSION` (render + route tests first)
- [X] T047 [US5] Diagnostics page: `/diagnostics` + `GET /api/diagnostics/all` (pdf, local-llm, browser-preflight, embeddings, source-reachability with real error text + timings), `GET /api/diagnostics/logs` zip export, `POST /api/diagnostics/cleanup-legacy-browser`; chromium-launch-selftest gains error text (tests first in tests/test_diagnostics.py)
- [X] T048 [US5] Installer hardening in packaging/windows.iss: `AppMutex=JobEngineRunning`, `CloseApplications=yes`, `RestartApplications=no`, `VersionInfoVersion`, stale-payload cleanup, `[Run]` relaunch entry gated on `/STARTAPP` param
- [X] T049 [US5] CI (.github/workflows/release.yml): publish SHA-256 of each asset in the release body; assert git tag == windows.iss version == engine.APP_VERSION at build time
- [X] T050 [US5] macOS: updater returns manual-download path for .dmg (no silent install), documented in USER_MANUAL
- [X] T051 [US5] Upgrade-with-data test: fixture v0.7-shape populated DB → migrations produce correct schema/data + backup file (tests/test_db.py), documented as release gate in quickstart

## Phase 8: US6 — Smarter matching within free limits (P6)

- [ ] T052 [test] [US6] Failing tests in tests/test_semantic.py: embed(text)→vector via fake embedder, cosine hybrid blend with keyword score, rank ordering stable, missing model/embedding degrades to keyword order (never blocks feed)
- [ ] T053 [US6] Implement engine/semantic.py (EmbeddingGemma via llama-cpp-python embedding mode) + pipeline integration: embed new jobs + resume, rank before scoring, LLM scores top-N within cap; bundle gguf in packaging/jobengine.spec with size assertion
- [ ] T054 [US6] Cloud model split: `LLM_JSON_MODEL` (strict structured outputs on Groq gpt-oss-120b) used by extraction/scoring paths in engine/matcher.py + engine/resume_extract.py; prose stays LLM_MODEL; tests first (request payload asserted)
- [ ] T055 [US6] Local tier constrained decoding: llama-cpp json_schema/grammar for structured outputs in engine/matcher.py local path (tests with stub llama); provider presets (Groq/Gemini co-equal + documented fallbacks with limits + privacy caveats) in settings.html + engine/settings.py

## Phase 9: Polish & Ship

- [ ] T056 Final gate, in order: (1) update README.md, USER_MANUAL.md, USER_GUIDE.md (new Apply Assist, watchlist, updater, diagnostics, What's New, 14-day default, provider presets); (2) bump 0.8.0 everywhere (engine/__init__.py, windows.iss, jobengine.spec) + changelog entry; (3) extend packaging/smoke_test.py (embeddings selftest, preflight answers, update-check dry run, version triple-match, ALLOW_DOWNLOADS honored); (4) full pytest ×2; (5) live frozen-shell walkthrough per quickstart.md §Shell walkthrough with content assertions; (6) merge → mirror `001-ai-job-engine` → tag v0.8.0 → both CI installers green → verify both Release assets

## Dependencies

- Setup (T001-T002) → Foundational (T003-T005) → all user stories.
- US1 (T006-T013) independent after Foundational. US2 (T014-T021)
  independent; T016 before frozen-shell verification of any story.
- US3: T022-T027 sequential (db → pipeline → liveness); T028-T030 need
  T005; T031-T035 parallel-friendly [P] after T023.
- US4: T036-T039 sequential; T040-T042 after T037; T042 touches
  jobspy_source with T031 — coordinate (same file, sequential).
- US5: T043-T045 sequential; T046-T047 [P]; T048-T049 before T044's
  install handoff can be live-tested; T051 after T004.
- US6 after US3's pipeline changes (same file). Polish last.

## Implementation strategy

MVP = US1 + US2 (the user's two burning complaints, independently
shippable and testable in the shell). Then US3 → US4 → US5 → US6 in
priority order, each ending green (full suite) before the next starts.
