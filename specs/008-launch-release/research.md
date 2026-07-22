# Research Decisions — Feature 008 (Launch Release)

All decisions below were produced by the 2026-07-22 audit + research fleet
(4 code audits with file:line evidence, 3 web-research agents with source
URLs, 1 completeness critic) and approved by the user where marked.

## 1. Apply Assist browser engine (USER-APPROVED)

- **Decision**: `playwright.sync_api` `chromium.launch_persistent_context(
  user_data_dir=<data_dir>/browser-profile, channel="msedge",
  headless=False)`, falling back to `channel="chrome"`, then a specific
  actionable error. Remove the first-use Chromium download flow.
- **Rationale**: Playwright channels locate the installed branded browser —
  nothing is downloaded, `PLAYWRIGHT_BROWSERS_PATH` becomes irrelevant, and
  the entire failed-download/stuck-"Installing…" defect class disappears.
  Edge ships inbox and is non-removable on US-market Windows 11; the EEA
  uninstall carve-out doesn't apply to this user. Packaging requirement:
  bundle only the Playwright Node driver (`playwright/driver` datas —
  already collected by `jobengine.spec`). Playwright is not thread-safe →
  keep the existing dedicated-thread sync-API pattern.
- **Alternatives rejected**: keep downloaded Chromium with better errors
  (280MB failure surface remains); WebDriver/Selenium (worse fit, new dep).

## 2. Desktop shell fixes (pywebview)

- **Decision**: pin `pywebview>=6.2`; `create_window(..., text_select=True,
  confirm_close=True, min_size=(960, 640))`; set
  `webview.settings["ALLOW_DOWNLOADS"] = True` and
  `webview.settings["OPEN_EXTERNAL_LINKS_IN_BROWSER"] = True` explicitly
  before `webview.start()`.
- **External links**: belt-and-suspenders. The WebView2 backend does open
  `target=_blank` externally via its NewWindowRequested handler when
  OPEN_EXTERNAL_LINKS_IN_BROWSER is on (verified in pywebview source), but
  behavior is backend/version-dependent — so additionally add
  `POST /api/open` (validates scheme ∈ {http, https}, `webbrowser.open`)
  plus a delegated JS click handler for `a[target=_blank]` that
  preventDefaults and posts the href. This also fixes the server-generated
  update link (`routes_api.py:316`) without touching Python strings.
- **Clipboard**: `navigator.clipboard` is permission-gated in WebView2 and
  pywebview registers no PermissionRequested handler (GitHub #1561 closed
  stale) → unreliable. Shared `window.copyText(text)`: try
  navigator.clipboard → fall back to hidden-textarea `execCommand("copy")`
  → final fallback `POST /api/clipboard` (host-side; PowerShell
  `Set-Clipboard` / `pbcopy`, no new hard dependency). Always toast
  success/failure. Replace the 3 inline `onclick` handlers
  (`job_detail.html:100,105,110`).
- **Downloads**: ALLOW_DOWNLOADS=True fixes the silently-dead PDF export
  in the shell; smoke test must assert it in shell mode.

## 3. Self-update (Windows)

- **Decision**: custom ~150-line updater in `engine/updates.py` (pyupdater
  is archived; tufup's TUF archive model doesn't drive Inno installers).
  Flow: GET `releases/latest` → pick asset (`JobEngine-Setup-*.exe` on
  Windows / `*.dmg` on macOS) → stream to `data_dir()/updates/` with
  Content-Length progress → verify SHA-256 published in the release body
  (CI adds it) → `Popen([exe, "/VERYSILENT", "/SUPPRESSMSGBOXES",
  "/NORESTART", "/STARTAPP=1"], DETACHED_PROCESS)` → app exits.
  Relaunch via an Inno `[Run]` entry gated on a Check function reading
  `/STARTAPP` (RestartApplications can't restart apps that never call
  RegisterApplicationRestart — PyInstaller apps don't).
- **Installer hardening (prerequisites)**: `AppMutex=JobEngineRunning`
  (desktop.py acquires via `ctypes.CreateMutexW`), `CloseApplications=yes`,
  `RestartApplications=no`, `VersionInfoVersion={#MyAppVersion}`, stale
  PyInstaller-payload cleanup, CI assertion tag == windows.iss #define ==
  `engine.APP_VERSION`. Startup check throttled to once/day, silent
  offline; macOS stays manual (documented).
- **SmartScreen**: app stays unsigned this release; the updater surfaces a
  blocked-installer state with the manual "More info → Run anyway" doc
  link. Code signing remains deferred.

## 4. Sourcing stack (freshness + genuineness)

- **Decision**: employer-direct-first. (1) Primary: no-auth ATS JSON
  boards — Greenhouse `boards-api…/jobs?content=true`
  (first_published/updated_at), Lever `api.lever.co/v0/postings`
  (createdAt epoch-ms), Ashby `posting-api/job-board` (publishedDate),
  Workable widget API — driven by a DB-backed watchlist seeded with 300+
  curated slugs (from open slug directories, e.g. the 20k-company
  job-board-aggregator index, curated toward CE/hardware/semis/defense +
  known sponsors). SmartRecruiters de-prioritized (now API-key-gated) but
  existing seeds kept while they still respond. (2) jobspy 1.1.82 limited
  to Indeed + Google, `hours_old=336` passed **alone** (it is mutually
  exclusive with job_type/is_remote/easy_apply on Indeed/LinkedIn — do
  those filters client-side; Glassdoor/Zip round hours_old up to full
  days). (3) LinkedIn: opt-in scraping with rate-limit warning (verified:
  unauthenticated LinkedIn 429s within a few hundred results; sustained
  use needs paid proxies → violates $0) + always-available link-out URLs
  (`linkedin.com/jobs/search/?keywords=…&f_TPR=r1209600`). (USER-APPROVED)
- **Freshness**: 14-day default window end-to-end — new `14d` display
  window (default), jobspy `hours_old=336`, ingest-time gate skipping
  date-bearing rows older than 14 days, and honest dates (rows with NULL
  posted_date display as approximate "seen <date>" instead of silently
  using first_seen as posted).
- **Dead postings**: `jobs.last_seen_at` stamped on every upsert;
  full-board sources mark rows absent from a *successful* fetch as
  `delisted` (absence is authoritative because boards are fetched in
  full); scraped-board rows get throttled HEAD checks (404 or
  redirect-to-careers-home ⇒ dead). Never mass-delist on a failed fetch.
- **Dedup fix**: same-source reposts (new URL, same dedup_key) currently
  insert duplicates (`db.py:279-280` excludes same source) → dedupe on
  key regardless of source, keeping the earliest row and refreshing URL.

## 5. AI tiers & ranking

- **Decision**: keep three tiers, upgrade each; add semantic pre-rank.
  - Cloud: Groq stays default; JSON/structured tasks move to
    `openai/gpt-oss-120b` (the only Groq models with guaranteed
    schema-valid strict structured outputs; 1K req/day, 200K tok/day
    free), prose (bullets/cover letters) stays `llama-3.3-70b-versatile`
    (verified still served free, 100K tok/day). New `LLM_JSON_MODEL`
    setting beside `LLM_MODEL`.
  - Provider presets in Settings: Groq + Google AI Studio (Gemini 2.5
    Flash free tier, ~1,500 req/day, 1M context, OpenAI-compatible
    endpoint, no card) as co-equal; Mistral (1B tok/mo free but
    training-data caveat disclosed), Cerebras (8K ctx cap), OpenRouter /
    GitHub Models (~50 req/day) listed as documented fallbacks. All are
    just base-URL+model presets around the existing provider-agnostic
    client (Constitution II).
  - Local: enable llama.cpp `response_format`/GBNF grammar-constrained
    decoding for structured outputs (research: grammar enforcement makes
    even 3B models emit valid JSON every time — immediate reliability win
    on the current bundled model). Optional Qwen3-4B upgrade deferred
    (out of 008 scope — avoids +2.5GB and a new download flow).
  - Semantic pre-rank: EmbeddingGemma-300M GGUF (Q8_0 ≈ 330MB, official
    ggml-org repo) via the already-bundled llama-cpp-python — no new
    packages, fully offline. Hybrid score = cosine(resume, job) blended
    with the existing keyword overlap; LLM scores top-N first within the
    per-run cap. Research basis: embedding-rank + LLM-rerank beats raw
    LLM scoring of everything (ConFit v3, Resume2Vec; MiniLM-class
    baselines) and stretches free quotas. Bundled in installer (project
    precedent: core-scoring assets are bundled).

## 6. Profile auto-fill + profile-driven search

- **Decision**: extend `ResumeSections` with `contact` (first/last name,
  email, phone, linkedin_url, portfolio_url, location) + `target_titles`;
  same `_extract_json` + bounded-retry idiom. Deterministic regex
  fallback (email/phone/URLs from the resume's first ~15 lines) so
  auto-fill works on the basic tier. Fill-only-blank; conflicts surface
  through the existing `extraction_conflict` consent pattern
  (`sections_edited_at` precedent). Visa/work-auth fields are never
  auto-filled (explicit confirmation only). New `engine/search_terms.py`
  derives ≤8 capped terms from target_titles/experience titles/top
  skills → stored in `user_profile.search_terms`, editable on Profile;
  jobspy consumes terms × `target_locations` (also finally honoring that
  field's documented-but-unimplemented feed pre-fill), falling back to
  the current built-in constants when the profile is empty.

## 7. Feed usability

- **Decision**: sort select auto-applies (`onchange` submit / hx-get);
  segmented window/view links rebuilt from the full current query string
  (already in context); hidden inputs for seen/ineligible/view in the
  toolbar form; Prev/Next pager over the existing total/limit/offset;
  `source` filter param + select; fix `entry_level='0'` mapping to real
  False; clickable Posted/Match headers toggle sort.

## 8. What's New + Diagnostics + crash visibility

- **Decision**: `WHATS_NEW_SEEN_VERSION` setting; on first page load where
  it ≠ APP_VERSION show a dismissible What's New overlay fed by a
  versioned in-repo changelog dict; mark seen on dismiss. Diagnostics page
  (Settings section or `/diagnostics`) runs the existing three selftests +
  a new embeddings selftest + source-reachability ping, shows real error
  text, tails `app.log`, offers log export (zip to Downloads) and the
  legacy-Chromium "reclaim ~300MB" cleanup. Global `threading.excepthook`
  + `sys.excepthook` writing to app.log with a crash marker file surfaced
  on next launch.

## 9. Migration & release-gate safety

- **Decision**: before running `_MIGRATIONS`, copy `jobs.db` to
  `data_dir()/backup/jobs-v{old}.db` (keep last 2); restore + surface
  error on migration failure. Release gate adds: upgrade test against a
  real populated v0.7 database; frozen-shell E2E checklist (fresh install →
  onboarding → refresh ≥3 sources with >0 jobs → sort/copy/open-link/PDF
  inside the shell → Apply Assist opens Edge and fills a live test posting
  → update dry-run) with content assertions per the v0.4.0 lesson.

## Sources

pywebview docs/changelog + `edgechromium.py` source; pywebview #1561;
Playwright browsers/library docs + MS Edge Playwright docs; Inno Setup
CloseApplications/RestartApplications/cmdline docs;
klogic/inno-setup-with-self-update; PyPI python-jobspy 1.1.82; jobspipe
jobspy review; fantastic.jobs + cavuno ATS API references;
Feashliaa/job-board-aggregator; Adzuna/USAJOBS/RemoteOK terms; Groq
models/rate-limits/structured-outputs docs; Google AI Studio/Gemini free
tier; Mistral/Cerebras/OpenRouter/GitHub Models limits; unsloth Qwen3-4B
GGUF; ggml-org EmbeddingGemma-300M GGUF; insiderllm structured-output
guide; ConFit v3 (arXiv 2605.09760), Resume2Vec (MDPI).
