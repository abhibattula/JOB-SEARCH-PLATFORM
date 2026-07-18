# Tasks: 002 Desktop App, Eligibility, Coverage & Freshness

Executed with the hybrid workflow (TDD; verification before completion).

## Workstream B — Eligibility (US2)

- [x] B1 Failing tests: ITAR/clearance/US-person phrases + false-positive guards (`tests/test_filters.py`); default-hides-EXCLUDED, ineligible-only view, EXCLUDED-never-scored (`tests/test_db.py`); `ineligible=1` contract (`tests/test_api.py`)
- [x] B2 Regex-based negative patterns in `engine/filters.py` (word boundaries; "military" ≠ ITAR)
- [x] B3 `engine/db.py`: `query_jobs(ineligible=, include_ineligible=)`; `jobs_needing_score` skips EXCLUDED
- [x] B4 `web/routes_api.py` + `web/main.py`: `ineligible` param through `/api/jobs`, `/api/export`, pages; Ineligible nav link in `base.html`
- [x] B5 Reclassify the live DB with the new detector

## Workstream C — Coverage + freshness (US3)

- [x] C1 Record real fixtures: `smartrecruiters_sample.json` (+detail), `workable_sample.json` (v3 endpoint discovered — v1 widget returns empty as of 2026-07)
- [x] C2 Failing parser tests → `engine/ingest/smartrecruiters.py` (US-scoped via `country=us`, experience-level fed to classifier) and `engine/ingest/workable.py` (v3 POST)
- [x] C3 Register sources; extend `scripts/check_seeds.py` for both ATS types
- [x] C4 Seed expansion: 33 candidates validated live → 20 kept (Roblox, Verkada, Neuralink, SambaNova, Formlabs, Zipline, Axon, Rocket Lab, Astera Labs, xAI, Chime, Discord, Kraken, Etched, Cognition, Visa, Bosch, ServiceNow, Hugging Face, Netguru); 13 dead/empty dropped
- [x] C5 jobspy: 3 additional entry-level SWE/hardware search terms
- [x] C6 Failing prune test → `db.prune_old_jobs(days=45)` (status-none only) wired into `pipeline._post_ingest`
- [x] C7 Live refresh across all 8 source families

## Workstream A — Desktop app (US1)

- [x] A1 `pywebview` dependency; `desktop.py`: port pick, uvicorn thread, readiness poll, native window, browser fallback, clean shutdown; scheduler shared via `app.maybe_start_scheduler`
- [x] A2 Launchers: `run.bat` → desktop; new `run.sh`, `run.command`, `jobs.sh`; `.gitattributes` pins LF for shell scripts
- [x] A3 Verify on Windows: window process serves feed; fallback path exercised

## Docs & wrap-up

- [x] D1 Spec 002 artifacts; 001 spec cross-reference
- [x] D2 README / docs/MANUAL.md / docs/USER_GUIDE.md / quickstart updated (desktop launch, Ineligible view, new sources, Mac instructions)
- [x] D3 Full suite green; live spot-checks; commit; restart the user's server on new code
