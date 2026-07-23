# Implementation Plan: The Live Fill Engine (v0.9.0)

**Branch**: `009-live-fill-engine` | **Date**: 2026-07-23 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/009-live-fill-engine/spec.md`
**Design doc**: `docs/superpowers/specs/2026-07-23-feature-009-design.md`

## Summary

Rebuild Apply Assist's fill layer as a **live watcher**: one dedicated
worker thread owns all Playwright objects for the app session; a steady
~2s tick walks every frame of the open page, serializes+stamps fields in
one JS pass, classifies via per-ATS adapters (generic classifier
fallback), and idempotently fills empty, unfocused, recognized fields —
forever, while a job is current. Jobs open at their true form URLs
(Lever `/apply`, Ashby `/application`). A bundled practice application
proves the engine on the user's machine and doubles as a real-browser
regression suite. Profile import becomes a background extraction job
(chunked on the local tier so it finally fits the model) feeding an
explicit review screen. The offline model becomes the default AI tier
with automatic cloud fall-through.

## Technical Context

**Language/Version**: Python 3.11 (unchanged).
**Primary Dependencies**: unchanged (playwright 1.61 channel-launch,
llama-cpp-python, FastAPI/Jinja/HTMX, fpdf2, jobspy). No new packages.
**Storage**: no schema migration — import proposal is session-scoped
memory; one new settings key (`PREFER_LOCAL_LLM`).
**Testing**: pytest; NEW `pytest.ini` registering `browser` marker with
`addopts = -m "not browser"` (fast default suite); real-browser fixture
suite behind `-m browser`; existing 506 tests stay green (state-machine
tests retarget one monkeypatch seam).
**Target Platform**: Windows 11 primary; macOS builds unchanged.
**Project Type**: local-first desktop web app (unchanged).
**Performance Goals**: tick ≤ ~150ms on a settled page (≤15 frames ×
1 eval); fields fill within ≤2 ticks (~4s) of appearing; practice run
fully filled <10s from queue start; upload responds <2s.
**Constraints**: NEVER click any control (constitution III/005 —
structurally enforced: field query excludes clickables, FakeLocator
raises on click, invariant re-tested on the locator path); engine/ never
imports web/; $0; no request thread ever performs browser work.
**Scale/Scope**: 2 rebuild workstreams + practice/polish; est. ~40 tasks.

## Constitution Check (v1.1.1)

- **I. Speed-to-Value**: PASS — this makes the flagship apply capability
  actually function; every task maps to a confirmed defect or approved
  trust feature.
- **II. Zero-Subscription Cost**: PASS — no new services; offline-first
  default *reduces* external dependence; practice page is local.
- **III. API-First, Polite Ingestion / no bot-fighting, never
  auto-submit**: PASS — watcher only fills; never clicks; navigates only
  to the job's own public URLs; no protection bypass. The 1-line Ashby
  ingest change still uses the official public API payload.
- **IV. Reusable Core, Thin Web Layer**: PASS — worker/watcher/adapters/
  apply_urls/profile_import all in engine/; routes remain thin
  enqueue/read facades.
- **V. Tested Core Logic**: PASS — TDD throughout; plus the NEW
  real-browser fixture layer that unit fakes cannot cover (the verified
  gap that let a non-working engine ship twice).

No violations; no constitution amendment required.

## Project Structure

### Documentation (this feature)

```text
specs/009-live-fill-engine/
├── plan.md  research.md  data-model.md  quickstart.md
├── contracts/http-api.md
├── checklists/requirements.md (+ risk.md)
└── tasks.md
```

### Source Code (new/changed)

```text
engine/autofill/
├── worker.py        # NEW dedicated Playwright-owner thread + command queue
├── watcher.py       # NEW one-tick logic: frame walk, serialize+stamp, classify, fill, activity
├── apply_urls.py    # NEW posting URL → form URL resolution (pure)
├── adapters.py      # NEW per-ATS name/id/autocomplete → tag maps (pure)
├── browser_controller.py  # REWRITE: thread-safe facade; public API + state semantics preserved
└── fields.py        # FIX: [\s_-]* separators + synonyms; classify/match_option preserved
engine/
├── profile_import.py  # NEW background import state machine + proposal + apply
├── resume_extract.py  # EDIT: chunked map-reduce path for local tier (+_split_chunks/_merge)
├── local_llm.py       # EDIT: n_ctx 4096→8192 (param for tests)
├── matcher.py         # EDIT: PREFER_LOCAL_LLM in scoring_tier/_chat w/ cloud fall-through
└── settings.py        # EDIT: PREFER_LOCAL_LLM default "1"
engine/ingest/ashby.py # 1-line: prefer applyUrl
web/
├── routes_autofill.py # EDIT: status gains activity; practice route; rescan = force tick
├── routes_api.py      # EDIT: slim /api/profile; /api/profile/import{,/status,/proposal,/apply}
├── main.py            # EDIT: /practice page route, import partial route
├── static/app.js      # EDIT: attention helper (scroll+highlight), import polling
└── templates/
    ├── practice_apply.html + practice_frame.html  # NEW bundled practice application
    ├── partials/import_progress.html, import_review.html  # NEW
    ├── partials/autofill_status.html  # EDIT: live activity feed + guidance
    └── autofill.html, profile.html, settings.html  # EDIT
pytest.ini            # NEW: markers, addopts
tests/
├── test_watcher.py test_apply_urls.py test_adapters.py test_profile_import.py  # NEW
├── integration/test_autofill_fixture_pages.py + fixtures/ats_pages/*           # NEW browser-marked
└── (edits) test_browser_controller.py (seam), test_fields.py, test_resume_extract.py,
    test_local_llm.py, test_matcher.py, test_api.py, test_routes_autofill.py
packaging/smoke_test.py  # EDIT: activity key, import status, practice page
```

**Structure Decision**: established layout; all logic engine-side
(Constitution IV).

## Complexity Tracking

None — no constitution violations to justify. (The dedicated worker
thread replaces an undocumented multi-thread hazard; it reduces
complexity of reasoning, not adds it.)
