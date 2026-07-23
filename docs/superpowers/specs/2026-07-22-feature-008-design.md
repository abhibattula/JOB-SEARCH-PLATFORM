# Feature 008 — Launch Release (v0.8.0): Design Doc

**Date:** 2026-07-22 · **Status:** Approved by Abhinav (AskUserQuestion, this date)
**Branch:** `008-launch-release`

## Why this release exists

v0.7.0 shipped with every feature verified in a dev browser — but the app ships
inside a **pywebview (WebView2) desktop shell**, where text selection, the
clipboard API, `target="_blank"` links, and downloads all behave differently.
The user, on v0.7.0 (confirmed via footer), experienced:

- Apply Assist never opens a browser ("total waste", 3 versions running)
- Cannot copy any text anywhere in the app
- "Open posting" / update-download links do nothing
- Same canned search results regardless of profile; no 14-day window; no
  visible sort; stale/dead postings
- Check-for-updates is a link, not an update

008 is the launch-readiness release: fix the shell, rebuild Apply Assist's
browser layer, make sourcing genuine/fresh/profile-driven, add real in-app
updates, and gate the release on end-to-end verification **inside the frozen
shell**, not a dev browser.

## Confirmed root causes (audit evidence)

1. **Copy dead**: `desktop.py:97` never passes `text_select` (pywebview
   default False → selection disabled app-wide). The 3 copy buttons
   (`job_detail.html:100,105,110`) use `navigator.clipboard` with no
   `.catch` — WebView2 permission-gates it and pywebview registers no
   PermissionRequested handler → silent failure.
2. **Apply Assist dead-ends**: Chromium is a ~280MB first-use download;
   on failure `browser_setup` stores `failed: …` but `/api/autofill/status`
   only exposes the boolean → UI shows "Installing…" forever
   (`autofill.html:41-48`). At Start, any launch exception is swallowed
   into `_state.fell_back` (`browser_controller.py:190-200`) and the UI
   claims "complete it manually in the open browser window" when **no
   window exists**. `fell_back` conflates 4 distinct causes.
3. **External links/downloads**: no `webview.settings` set; `ALLOW_DOWNLOADS`
   defaults False (PDF export silently dead in shell); `_blank` handling is
   backend/version-dependent; the update "download it" link
   (`routes_api.py:316`) is a `_blank` inside the same shell.
4. **Sourcing static**: search terms are hardcoded (`jobspy_source.py:19-27`);
   profile/`target_locations` never influence sourcing; LinkedIn off by
   default; Workday ships 0 seeds; 67 ATS companies; jobspy 8-day window;
   no 14d option (24h/7d/all); no dead-posting detection; same-source
   repost dupes (`db.py:279-280`); `COALESCE(posted_date, first_seen)`
   misdates undated rows.
5. **Sort exists but hidden**: sort select doesn't auto-submit; segmented
   window/view links drop active filters; no pagination (>100 rows
   unreachable); `entry_level='0'` maps to None (dead code).
6. **Updater is a hyperlink**: `updates.check()` never reads assets, no
   download/install; installer lacks AppMutex/CloseApplications/VersionInfo;
   version string triplicated with no assertion.

## Decisions (user-approved)

| Decision | Choice |
|---|---|
| Apply Assist engine | **User's installed Edge/Chrome** via Playwright `channel="msedge"` → `"chrome"` → clear error. Isolated persistent profile (own `user_data_dir`). Kills the Chromium download and its whole failure class. `PLAYWRIGHT_BROWSERS_PATH` becomes irrelevant; bundle only the Node driver. |
| LinkedIn | Opt-in scraping with honest rate-limit warning + always-available "Search this on LinkedIn" link-outs (genuine, $0-safe). |
| Release shape | One **v0.8.0** launch release. |
| Never-auto-submit | Unchanged (Constitution). UI states plainly that the final submit/login click is always the user's. |

## Workstreams

### WS-A Desktop shell correctness
- `create_window(..., text_select=True, confirm_close=True, min_size=(960,640))`;
  `webview.settings['ALLOW_DOWNLOADS']=True`, `OPEN_EXTERNAL_LINKS_IN_BROWSER=True` explicit.
- `POST /api/open` (validates http/https, `webbrowser.open`) — guaranteed
  external-open path; delegated JS click handler intercepts `a[target=_blank]`
  → posts to it (also fixes the server-generated update link).
- Clipboard: shared `copyText()` → try `navigator.clipboard`, fall back to
  textarea+`execCommand('copy')`, final fallback `POST /api/clipboard`
  (host-side); always toast success/failure.
- **Copy link** button on every feed row + job detail; raw URL visible on detail.

### WS-B Apply Assist rebuild (browser layer + truth-telling UI)
- `launch_persistent_context(user_data_dir=…, channel="msedge", headless=False)`,
  fallback chain msedge → chrome → actionable error. Remove the Enable/download
  flow entirely (keep a one-time "connect browser" preflight card).
- Replace `fell_back: set` with `job_id → {reason, detail}`
  (`launch_failed | nav_failed | scan_failed | unrecognized`); distinct UI
  messages; preflight self-test before queue start; Diagnostics page runs the
  3 existing self-tests + tails app.log + export-logs button.
- Startup resets stale `installing` status; migration drops the old
  chromium-status gating.

### WS-C Genuine, fresh, wider sourcing
- 14-day freshness end-to-end: jobspy `hours_old=336` (passed alone —
  mutual-exclusivity respected), new `14d` feed window as **default**,
  ingest-time age gate for ATS boards, stop COALESCE-misdating (fall back to
  first_seen only when posted_date is null AND flag `~` approx in UI).
- Dead-posting detection: `last_seen_at` on every upsert; full-board ATS
  fetches mark absent jobs `delisted` (hidden/badged); HEAD-check apply URLs
  for scraped rows (404/redirect-to-home ⇒ dead).
- Seeds: 67 → 300+ curated Greenhouse/Lever/Ashby/Workable slugs (from open
  slug directories, curated toward CE/hardware/new-grad + known sponsors);
  company watchlist editable in Settings (DB-backed, seeded once from YAML).
- jobspy: add Google Jobs; LinkedIn opt-in + link-out buttons; expose
  results_wanted/sites/terms/locations as settings; close same-source dedup
  hole; raise MAX_SCORE_PER_RUN in step with volume.

### WS-D Profile auto-fill + profile-driven search
- Extend `ResumeSections` with `contact` (first/last/email/phone/linkedin/
  portfolio/location) + `target_titles`; regex fallback (email/phone/URL from
  header lines) for the no-AI tier. Fill-if-blank; conflicts surfaced via the
  existing `sections_edited_at`-style consent pattern. Never auto-fill
  visa_status without confirmation.
- New `engine/search_terms.py`: derive capped, **editable** search terms from
  resume sections/skills → `user_profile.search_terms`; jobspy consumes them +
  `target_locations` (fallback: current constants). Profile page shows and
  edits them.

### WS-E AI tiers + ranking
- Groq default stays `llama-3.3-70b-versatile` for prose (verified live,
  free); JSON tasks → `openai/gpt-oss-120b` strict structured outputs.
  Provider presets: + Google AI Studio (Gemini 2.5 Flash free) co-equal;
  Mistral/Cerebras/OpenRouter/GitHub Models documented fallbacks.
- Local tier: llama.cpp grammar/json_schema-constrained decoding now
  (reliability win on current model); optional Qwen3-4B Q4 (~2.5GB) download
  for 8GB+ machines.
- **Embeddings pre-rank**: EmbeddingGemma-300M GGUF (~330MB, existing
  llama-cpp-python stack) hybrid semantic+lexical ranking; LLM scores only
  top-N. Biggest relevance lever + stretches free quotas.

### WS-F In-app self-update
- `updates.check()` selects platform asset (`JobEngine-Setup-*.exe` /
  `*.dmg`) → `browser_download_url` + size; startup check (throttled 1/day,
  silent offline) → dismissible banner.
- Download to `data_dir()/updates` with progress; SHA-256 from release body;
  launch `/VERYSILENT /SUPPRESSMSGBOXES /NORESTART` detached; app exits;
  relaunch via guarded [Run] entry. macOS: stays manual (documented).
- Installer hardening: AppMutex (`JobEngineRunning`, acquired in desktop.py),
  `CloseApplications=yes`, `RestartApplications=no`, VersionInfoVersion,
  stale-file cleanup strategy, CI assertion that tag == iss == APP_VERSION.

### WS-G Launch gate & polish
- Sort select auto-applies; segmented links preserve full query; Prev/Next
  pagination; source filter; fix `entry_level='0'`; clickable Posted/Match
  headers.
- "What's New" screen post-update (fixes "I don't see what changed");
  onboarding refreshed for new flows.
- DB: backup jobs.db before migrating; upgrade tested against a real
  populated v0.7 DB. Crash marker + global thread excepthook → app.log.
- Release gate exercised **in the frozen shell**: fresh install → onboarding →
  refresh >0 jobs from ≥3 sources → sort/copy/open-link → Apply Assist opens
  Edge and fills a live test posting → update flow. Content-asserting checks
  (v0.4.0 lesson). SmartScreen/unsigned friction documented; code signing
  remains deferred.

## Out of scope
Auto-submit/auto-login (banned), paid proxies, LinkedIn auth automation,
code signing, browser extension, multi-user.

## Sources
Audit + research fleet 2026-07-22 (4 code audits with file:line evidence;
jobspy/PyPI, Groq/Gemini/Mistral docs, pywebview docs+source, Playwright
docs, Inno Setup docs, ATS API references, ConFit v3 / Resume2Vec papers).
