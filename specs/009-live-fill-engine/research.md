# Research Decisions — Feature 009 (The Live Fill Engine)

Grounded in the two 2026-07-23 root-cause investigations (verdicts + all
file:line evidence recorded in the design doc and Claude plan file) and
the Plan-agent architecture study.

## 1. Root-cause verdicts driving the design

- A1 scan-at-load (goto → immediate one-shot serialize; JS forms not yet
  mounted) — **sufficient alone**; fixed by the watch loop.
- A2 posting-URL ≠ form-URL (Lever `/apply`, Ashby `/application`,
  Workable/Indeed posting pages) — **sufficient alone**; fixed by
  `apply_urls` + Ashby ingest preferring `applyUrl`.
- A3 no retry mechanism; A4 iframe-blind; A5 greenlet-unsafe
  `framenavigated` handler (multi-page refill silently never worked);
  A6 Playwright touched from multiple request threads (docstring claimed
  a dedicated thread that never existed) — all fixed structurally by the
  worker + watch loop; the `framenavigated` handler is deleted.
- A7 classifier `\s*` never matches `first_name`-style attributes; A8
  selectors built from raw ids/names malformed for bracket names — fixed
  by regex separators `[\s_-]*` and stamp-based addressing.
- B1 synchronous in-request extraction with zero feedback; B2 local-tier
  context overflow (n_ctx=4096 vs 24,000-char prompt → 100% silent
  failure); B3 invisible fill-only-blank semantics — fixed by the
  background import state machine, chunked local extraction, and the
  review screen.

## 2. Worker thread + command queue (WS-A core)

- **Decision**: one daemon thread (`apply-assist-worker`) created lazily,
  alive for the app session; a `queue.Queue` of commands (`OPEN_JOB |
  FORCE_TICK | CLOSE_PAGE | RESOLVE_PENDING | SHUTDOWN_CONTEXT`). The
  `queue.get(timeout=TICK_SECONDS)` wait IS the scheduler: commands
  preempt instantly; on timeout, if a job is current and not interrupted,
  run one watch tick. Every Playwright-touching function begins with
  `_assert_worker_thread()`. Facade functions mutate `_State` under the
  existing lock synchronously (so `current_job()`/tests see consistent
  state immediately) and enqueue; **no route ever blocks on browser
  work** (only `RESOLVE_PENDING` may wait ≤0.5s for an ack).
- **Rationale**: makes Playwright's same-thread rule impossible to
  violate; deletes the greenlet-unsafe event-callback pattern entirely;
  `start_queue` stops blocking requests for up to 30s.
- **Alternatives rejected**: async API + event loop thread (larger
  rewrite, sync API already shipped); per-call thread confinement checks
  without a queue (leaves ordering races).

## 3. Watch tick (WS-A behavior)

- **Decision**: steady cadence `TICK_SECONDS = 2.0` (clarified: no idle
  backoff). Per tick: walk `page.frames` (skip blank/about:blank, cap
  `MAX_FRAMES = 15`); per frame ONE `frame.evaluate` that both serializes
  descriptors (tag/type/name/id/label/placeholder/aria/autocomplete/
  value/options + `focused` + `visible`) AND stamps un-stamped elements
  `data-je-idx=<n>` from a page-scoped counter; classification =
  `adapters.classify(ats_from_frame_url, d)` → fallback
  `fields.classify(d)`; fill only when: value empty AND not focused AND
  `(frame_key, je_idx)` not already filled AND a value resolves; re-check
  empty+unfocused via the locator immediately before writing; act via
  `frame.locator('[data-je-idx="N"]')` with the existing
  `_apply_field_value` (fill/select_option(label)/check/set_input_files —
  never click). React re-mounts produce fresh unstamped nodes → refilled
  if empty (self-healing); fill-report rows deduped by (frame, idx).
  Serialization errors tolerate 3 consecutive failures before recording
  `scan_failed` (cleared by a later success). `unrecognized` is no longer
  a produced terminal state.
- **Rationale**: covers late renders, user-revealed forms, multi-page
  flows, and iframes with ONE mechanism; stamp addressing kills the
  selector-escaping class; the focused-guard + pre-write re-check bounds
  the typing race to milliseconds.
- **Alternatives rejected**: MutationObserver push (needs page-side
  bindings + still polls for iframes; more moving parts); Playwright
  `expect`/wait_for_selector per field (unknown selectors upfront).

## 4. Apply-URL resolution + Ashby ingest

- **Decision**: pure `apply_urls.resolve(job) -> str` — host/path match:
  `jobs.lever.co/<org>/<id>` → append `/apply` (idempotent);
  `jobs.ashbyhq.com/<org>/<id>` → append `/application` (idempotent);
  Greenhouse hosts as-is; everything else as-is. Plus `ashby.py` stores
  `applyUrl or jobUrl` going forward. Query/fragment preserved.
- **Rationale**: evidence-verified form locations; unknown hosts degrade
  to the watcher + on-screen guidance ("click the site's Apply button").

## 5. Per-ATS adapters + generic classifier fixes

- **Decision**: `adapters.py` maps exact `name`/`id` values per ATS
  (Greenhouse: `first_name`, `last_name`, `email`, `phone`, `resume`,
  `cover_letter`, `job_application[...]` variants; Lever: `name`,
  `email`, `phone`, `org`, `resume`, `comments`, `urls[LinkedIn]`,
  `urls[GitHub]`, `urls[Portfolio]`; Ashby: `_systemfield_name/email/
  phone/resume`), plus a shared HTML `autocomplete` map (given-name/
  family-name/name/email/tel/url). ATS detected from the **frame URL
  host** (not job.source — jobspy rows often carry ATS-hosted URLs).
  Adapter maps are seeded from known markup and verified against the
  fixture pages + live gate; a stale map degrades to the generic
  classifier. `fields.py`: separators become `[\s_-]*` (first/last/full
  name, years-experience, how-heard, salary, cover-letter, website
  patterns), tested against real raw attribute descriptors.
- **Rationale**: deterministic on the three boards that dominate the
  watchlist; graceful elsewhere.

## 6. Practice application (WS-A+)

- **Decision**: `web/templates/practice_apply.html` (+
  `practice_frame.html` embedded via iframe) served at `/practice/apply`
  by the app itself; fields: first/last name, email, phone, LinkedIn,
  resume file input, work-authorization `<select>` (option-matching),
  one custom free-text question, one section rendered after a 1.5s JS
  delay, one section inside the iframe. "Test Apply Assist" button
  queues a synthetic practice entry (special job id 0 / dedicated
  `OPEN_PRACTICE` payload carrying the local URL — no DB row needed) and
  runs the normal engine end-to-end. The same page family (plus Lever/
  Ashby-attribute and typing-race variants under
  `tests/fixtures/ats_pages/`) is the browser-marked regression suite.
- **Rationale**: ten-second on-machine proof; fixture and product are the
  same artifact class, so the demo IS the regression test.

## 7. Background import + chunked local extraction (WS-B)

- **Decision**: `engine/profile_import.py` clones the proven
  `updates.py` `_state+_lock+daemon-thread` state machine (`idle →
  extracting(stage: contact→skills→sections i/N) → ready(proposal) →
  applied | failed(error)`; `background=False` test path; 409 on
  concurrent start). `POST /api/profile` stores file/text/form fields
  only and triggers import; **no inline LLM calls** (enforced by a
  monkeypatch-to-raise test). Local tier: `local_llm` `n_ctx` → 8192
  (Qwen2.5-1.5B supports 32k; KV cost at 8k acceptable) AND chunked
  map-reduce in `resume_extract`: `_split_chunks(text, target≈5000)` on
  blank-line boundaries; per-chunk prompt = existing `_SYSTEM` + "part
  i/N — extract only what appears here"; grammar-constrained JSON
  (existing 008 lever); `_merge`: ordered concat for
  experience/education/projects, casefold-deduped union for
  skills/target_titles, first-non-empty contact overlaid with the regex
  fallback; one bounded retry per chunk; all-chunks-failed → None,
  else partial. Cloud tier keeps single-shot. Regression test: every
  local prompt ≤ ~6000 chars.
- **Rationale**: chunking is the fidelity fix (small models extract
  small contexts well) and yields natural progress UI; 8192 gives
  headroom and fixes any other near-cliff local caller. Raising n_ctx
  alone rejected: single-shot 24k prompts degrade a 1.5B model's output
  and still risk truncation.

## 8. Review screen semantics

- **Decision**: proposal lists EVERY field (identity 6 + skills +
  target_titles + target_locations + resume_sections summary) as
  `{current, proposed, default}`; defaults blank→apply, conflict→keep,
  lists→merge, edited-sections→keep+warning; zero-diff proposals render
  the compact "everything already matches" confirmation with expandable
  detail (clarified). `apply` = one `db.save_profile(**updates)`;
  applying sections sets/clears `sections_edited_at` per the existing
  consent rule and supersedes the old re-extract prompt; search terms
  re-derived unless `derived_from == "user"`; visa/work-auth never in the
  proposal (FR-024 lineage). Old `PENDING_IDENTITY_CONFLICTS` flow stops
  being generated (endpoint kept one release for compat).

## 9. Offline-first tier preference

- **Decision**: `PREFER_LOCAL_LLM` default `"1"` (user decision).
  `matcher.scoring_tier()`: local model available AND preference on →
  `"local"` even with a key; `_chat` dispatches off `scoring_tier()` and
  on local-tier exception falls through to cloud when a key exists
  (else re-raises). Settings checkbox copy: "Prefer the bundled offline
  model (private, $0, slower) — cloud key remains the automatic backup."
- **Impact note**: scores render with the `•` local marker by default;
  documented in USER_MANUAL.

## 10. Verification architecture

- `pytest.ini` (NEW): `markers = browser`, `addopts = -m "not browser"`.
  CI/pre-release adds an explicit `pytest -m browser` job step (Windows
  runner has Edge; headless via `AUTOFILL_HEADLESS=1` env honored by
  `_ensure_context`; skip cleanly when no channel launches).
- Fixture pages: delayed-render Greenhouse-style (A1 regression), iframe
  host+frame (A4), Lever bracket-names (A8), Ashby `_systemfield_*`,
  form-behind-Apply-button (the TEST clicks; the watcher fills),
  typing-race (focused-guard). Harness: `ThreadingHTTPServer` on an
  ephemeral port; poll `queue_snapshot()` until expected fills; assert
  real DOM values.
- Live gate (quickstart): one real Greenhouse/Lever/Ashby/Indeed posting
  each; frozen smoke: `activity` key, import status idle, practice page
  serves; offline-tier gate: real chunked extraction of a 3-page fixture
  resume produces ≥1 experience entry.
