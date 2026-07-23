# Implementation Plan: Launch Release (v0.8.0)

**Branch**: `008-launch-release` | **Date**: 2026-07-22 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/008-launch-release/spec.md`
**Design doc**: `docs/superpowers/specs/2026-07-22-feature-008-design.md`

## Summary

Make the app launch-ready by fixing the class of defects that only exist in
the shipped desktop shell (selection/clipboard/links/downloads dead),
rebuilding Apply Assist's browser layer on the user's installed Edge/Chrome
(removing the failure-prone Chromium download entirely), making sourcing
genuine + fresh (14-day default end-to-end, delisting, 300+ direct company
boards, profile-driven search), auto-filling profile identity from the
resume, adding an offline semantic pre-ranking stage plus schema-reliable
cloud extraction, and shipping true in-app self-update with an installer
hardened for unattended upgrades. Release gate runs inside the frozen
pywebview shell — the blind spot that let 007's defects ship.

## Technical Context

**Language/Version**: Python 3.11 (unchanged)
**Primary Dependencies**: FastAPI + Jinja2 + HTMX (vendored), httpx,
PyMuPDF, rapidfuzz, python-jobspy 1.1.82, playwright (channel-based —
`msedge`/`chrome`, Node driver bundled, no browser download), fpdf2 2.8.7,
llama-cpp-python (existing; + grammar/json_schema constrained decoding; +
EmbeddingGemma-300M Q8_0 GGUF ~330MB bundled for embeddings), pywebview
**pinned ≥ 6.2** (WebView2 backend), keyring, PyInstaller + Inno Setup.
**Storage**: SQLite at `data_dir()/jobs.db` via `engine/db.py` migrations
(new: `jobs.last_seen_at`, `jobs.delisted`, `jobs.embedding`,
`user_profile.search_terms`, `user_profile.resume_embedding`, new
`watchlist` table). Update artifacts under `data_dir()/updates/`; DB backup
before migration at `data_dir()/backup/`.
**Testing**: pytest (405+ existing tests stay green). TDD per constitution
V for all deterministic logic: reason-class mapping, delisting diff,
dedup fix, 14d window, search-term derivation, contact regex fallback,
update version/asset selection + SHA-256 verify, watchlist CRUD, embedding
rank ordering (with a fake embedder), settings plumbing.
**Target Platform**: Windows 11 primary (user's machine); macOS builds
continue but self-update stays manual there (documented).
**Project Type**: Local-first desktop web app (FastAPI server + pywebview
shell), frozen with PyInstaller.
**Performance Goals**: Apply Assist browser visible < 15 s from Start
(SC-001); embeddings rank 500 jobs < 60 s on CPU; update download shows
progress at least every second.
**Constraints**: $0 recurring (all providers free-tier, all sources
public/no-card); never auto-submit/auto-login/click; polite ingestion
(≤1 req/s/domain, honest UA); engine/ never imports web/; installer stays
a single offline-capable artifact (embeddings model bundled ≈ +330MB).
**Scale/Scope**: single user; ~300-500 watchlist boards; feed up to a few
thousand rows; 7 workstreams (WS-A…WS-G per design doc), est. ~50 tasks.

## Constitution Check

*Constitution v1.1.0 → amended to v1.1.1 in this feature (see below).*

- **I. Speed-to-Value**: PASS — every workstream maps to a user complaint
  blocking real applications (broken shell, dead Apply Assist, stale
  postings, manual profile, no updates). No deferred capability
  (auth/multi-user/hosted/CLI-MCP) is built.
- **II. Zero-Subscription Cost**: PASS — installed-browser automation
  ($0), GitHub Releases self-update ($0), free AI tiers only (Groq,
  Google AI Studio presets; limits stated in-app), public ATS JSON feeds,
  jobspy Indeed+Google. LinkedIn scraping stays opt-in because sustained
  scraping would require paid proxies (rejected); link-outs are $0.
- **III. API-First, Polite Ingestion**: PASS — new sources are official
  public JSON (ATS boards); apply-URL liveness checks are HEAD requests
  throttled to the same 1 req/s/domain budget and only for scraped-board
  rows; delisting uses board-diffing (no extra requests). Playwright
  drives the user's own browser for the user's own applications — no bot
  protection is bypassed; never auto-submit/auto-login unchanged (FR-011).
- **IV. Reusable Core, Thin Web Layer**: PASS — updater, watchlist,
  search-term derivation, embeddings, delisting all live in `engine/`;
  `web/` gains thin routes; `desktop.py` (shell launcher) is the only
  place pywebview is touched. Full pipeline remains headless-runnable.
- **V. Tested Core Logic**: PASS — TDD required for all deterministic
  logic listed in Testing above; LLM outputs stay pydantic-validated with
  bounded retry; unscored jobs still appear (semantic rank is a fallback
  ordering, not a gate).
- **Amendment required (user-directed)**: the Additional Constraint
  "default feed view is the past 7 days" changes to "a recent window
  (14 days by default, 24h/7d/all toggles)" per the user's explicit
  instruction. Constitution bumped to **v1.1.1** (wording/default change,
  PATCH) as part of this feature — see Complexity Tracking.

## Project Structure

### Documentation (this feature)

```text
specs/008-launch-release/
├── plan.md              # This file
├── research.md          # Phase 0 decisions
├── data-model.md        # Phase 1 schema/entities
├── quickstart.md        # Phase 1 verification walkthrough
├── contracts/http-api.md
├── checklists/requirements.md
└── tasks.md             # /speckit.tasks output
```

### Source Code (repository root — existing layout, changed/new files)

```text
desktop.py                     # shell fixes: text_select, settings, confirm_close, AppMutex, update handoff
engine/
├── db.py                      # migrations (last_seen_at, delisted, embedding, search_terms, watchlist), 14d window, dedup fix, backup-before-migrate
├── settings.py                # new keys: sites/results/terms caps, LLM_JSON_MODEL, WHATS_NEW_SEEN, UPDATE_* 
├── updates.py                 # asset selection, download w/ progress, SHA-256 verify, install handoff
├── watchlist.py               # NEW — DB-backed company watchlist (seeded from companies.yml)
├── search_terms.py            # NEW — derive capped terms from profile/resume
├── semantic.py                # NEW — EmbeddingGemma via llama-cpp-python; hybrid rank
├── resume_extract.py          # + contact/target_titles submodels + regex fallback
├── matcher.py                 # JSON-model split (strict cloud model), local grammar-constrained decoding
├── pipeline.py                # profile-driven terms, 14d ingest gate, delisting pass, embed+rank stage, scoring cap scaling
├── ingest/
│   ├── jobspy_source.py       # terms/locations from profile, hours_old=336 alone, +google site, settings knobs
│   ├── (greenhouse|lever|ashby|workable).py  # watchlist-driven, board-diff delist hook, ingest age gate
│   └── linkedin_linkout.py    # NEW — builds LinkedIn search URLs (no scraping)
└── autofill/
    ├── browser_controller.py  # channel launch (msedge→chrome), reason-class outcomes, preflight
    └── browser_setup.py       # REMOVED flow; replaced by preflight + legacy-dir cleanup helper
web/
├── main.py                    # 14d default, whats-new gate, diagnostics page route, watchlist/settings context
├── routes_api.py              # /api/open, /api/clipboard, watchlist CRUD, updates endpoints, search-terms PUT, sort/paging/source params, identity autofill flow
├── routes_autofill.py         # preflight route, reason-class status payload, setup route removed
├── static/app.js              # copyText(), external-link delegation, update progress, sort auto-apply
└── templates/                 # feed (sort/paging/copy/linkout), autofill (no download step), settings (watchlist, providers, update), diagnostics.html, whats_new partial, profile (terms editor, identity conflicts)
packaging/
├── jobengine.spec             # playwright driver + embedding gguf datas, version resource, asserts
├── windows.iss                # AppMutex, CloseApplications, VersionInfo, cleanup, /STARTAPP run entry
└── smoke_test.py              # + embeddings selftest, updater dry-run check, shell-mode assertions
companies.yml                  # expanded to 300+ curated seeds (one-time seed source)
tests/                         # new: test_watchlist, test_search_terms, test_semantic, test_updates, test_delisting; extended: browser_controller, ingest, db, api, settings
```

**Structure Decision**: keep the established single-repo layout
(engine/web/packaging/tests); all new logic is engine-side modules with
thin web routes, matching Constitution IV.

## Complexity Tracking

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| Constitution 1.1.0 "7-day default view" constraint changed | User explicitly directed a 14-day default ("okay to show reasonably old postings … past 2 weeks") | Keeping 7d default and adding a 14d toggle was rejected: the user's stated default preference is 14d; constitution amended to 1.1.1 rather than silently deviating |
| Installer grows ≈ +330MB (bundled embeddings model) | Semantic pre-rank is core scoring; project precedent bundles core-scoring assets (local LLM) and downloads only opt-in assets | On-demand download rejected: recreates the exact failure class (silent 300MB download) this release exists to kill |
