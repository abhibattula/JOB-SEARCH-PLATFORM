# Implementation Plan: The Pairing Release

**Branch**: `015-pairing` | **Date**: 2026-07-25 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/015-pairing/spec.md`
**Design doc**: `docs/superpowers/specs/2026-07-25-feature-015-design.md`

## Summary

Make Apply Assist trustworthy end-to-end by fixing the four machine-verified
failure layers: (1) serialize ALL on-device AI behind a single inference owner
(the unserialized llama calls caused the recorded `ggml-cpu.dll` access-
violation crash) and stop generating suggestions while holding the Apply Assist
facade lock (the chronic freeze); (2) rebuild companion pairing so every step
is verified and every failure is visible — dependency-free stamping with
read-back verification, a live connect wizard, popup diagnostics, and a
one-stop `/api/companion/doctor`; (3) honor a new preferred-browser setting
(default Chrome, D3) in link-opening and the assistant window, always
disclosing the active fill path (D2); (4) fix the evidenced session bugs
(confirm-answer FK 500, updater empty-download/locked-file failures, installer
hoard). The proven fill core is untouched. A time-boxed subprocess-isolation
spike (D1) decides GO/NO-GO by the packaged-build gate; the release ships
either way.

## Technical Context

**Language/Version**: Python 3.11+ (engine + FastAPI web), vanilla ES modules
(MV3 extension) — no build step
**Primary Dependencies**: existing only — FastAPI/Starlette, Jinja2 + HTMX
(vendored), llama-cpp-python (bundled models), Playwright channels, pydantic
(bridge validation only — now explicitly excluded from the stamp path);
NEW code uses stdlib only (`threading`, `queue`, `multiprocessing`, `winreg`)
**Storage**: SQLite `jobs.db` (settings keys); small JSON status files in the
data dir (`stamp_status.json`, `updates/cleanup.json`, `running.marker`,
existing `pairing.json`/`port.txt`); `chrome.storage.session` for the
extension's last-attempt record
**Testing**: pytest (default suite), `-m browser` real-browser integration
(Playwright persistent contexts, real Edge + real Chrome), `-m slow` offline
gates, `packaging/smoke_test.py` frozen gate (extended to gate stamping)
**Target Platform**: Windows 11 primary (all root-cause evidence), macOS via
existing CI dmg job; engine stays cross-platform importable (Linux CI)
**Project Type**: local desktop web app (FastAPI + pywebview shell) + unpacked
MV3 browser extension companion
**Performance Goals**: Apply Assist status responds < 1 s while AI generates
(SC-002); connect page reaches "Connected" < 60 s with companion loaded
(SC-004); AI calls bounded by explicit time budgets (chat 180 s, embed 30 s,
env-overridable)
**Constraints**: $0 / offline-first / no new third-party deps / engine never
imports web / never auto-submit / secrets fill-and-forget / no JS framework
**Scale/Scope**: 2 new engine modules (`inference.py`,
`autofill/bridge_const.py` [+ tiny `lifecycle.py`]), ~6 engine modules edited,
1 web route module edited + doctor endpoint, 3 templates reworked, 4 extension
files edited, ~10 new test files/classes, no DB schema migration (settings
keys + JSON files only)

## Constitution Check

*GATE: evaluated against constitution v1.1.3 — PASS (no violations; table not
needed).*

- **I. Speed-to-Value**: directly serves "complete and submit applications
  faster" — Apply Assist is currently untrustworthy (never-paired companion,
  crash/freeze mid-application). No deferred capability (auth/hosting/CLI-MCP)
  is touched. Automation rules unchanged: the fill core is untouched; nothing
  new clicks anything.
- **II. Zero-Subscription Cost**: all new code is stdlib; the companion stays
  an unpacked extension (no store fee); no new services.
- **III. Polite Ingestion**: no ingestion changes.
- **IV. Reusable Core, Thin Web Layer**: `engine/inference.py`,
  `bridge_const.py`, `lifecycle.py`, stamp/status logic live in engine/scripts;
  `web/` only composes them (doctor endpoint, banners). Engine imports no web
  module. The stamp path's import allowlist is enforced by a test.
- **V. Tested Core Logic**: deterministic additions get pytest first —
  serialization guarantee (stub-model concurrency hammer), stamp read-back +
  import allowlist (AST), FK guard, updater failure paths, channel-order
  preference logic, doctor freshness/port-match logic. Real-browser E2E covers
  the human pairing path in both Chrome and Edge; the frozen gate covers the
  installed app.

*Post-Phase-1 re-check: still PASS — no new dependencies or layer violations
introduced by the design artifacts.*

## Project Structure

### Documentation (this feature)

```text
specs/015-pairing/
├── plan.md              # This file
├── research.md          # Phase 0: decisions R1–R13 with rationale
├── data-model.md        # Phase 1: entities, files, settings keys, schemas
├── quickstart.md        # Phase 1: manual verification walkthrough
├── contracts/
│   ├── inference-api.md          # engine-internal serialization contract
│   ├── http-api-additions.md     # /api/companion/doctor, /api/os/default-apps, additive fields
│   └── bridge-protocol-additions.md  # Hello.browser (additive, protocol_v stays 1), reject counters
└── tasks.md             # Phase 2 (/speckit.tasks — not created by plan)
```

### Source Code (repository root)

```text
engine/
├── inference.py                  # NEW (R1): single-owner AI worker + timeouts (+ R2 subprocess seam)
├── lifecycle.py                  # NEW (R9): running.marker helpers (unclean-exit detection)
├── local_llm.py                  # EDIT: chat() routes through inference owner
├── semantic.py                   # EDIT: embed() routes through inference owner
├── updates.py                    # EDIT (R11): size gate, safe cleanup, deferred deletes, prune
├── settings.py                   # (used) PREFERRED_BROWSER, UNCLEAN_EXIT_* keys
└── autofill/
    ├── bridge_const.py           # NEW (R4): PROTOCOL_V/APP_ID, zero heavy imports
    ├── ext_protocol.py           # EDIT: import consts from bridge_const; Hello.browser (optional)
    ├── ext_backend.py            # EDIT: browser in status; reject counters (R5)
    ├── browser_controller.py     # EDIT (R3): park-pending w/o inference under _lock; channel order via preference
    └── default_browser.py        # EDIT (R6): effective_channel_order(); open_url() with App Paths

scripts/
└── stamp_extension.py            # EDIT (R4): allowlisted imports, always-write pairing, read-back verify,
                                  #            stamp_status.json, manifest version stamping (R13)

web/
├── routes_bridge.py              # EDIT (R5): /api/companion/doctor; record rejects on 4401/4426
├── routes_autofill.py            # EDIT (R10): confirm_answer sentinel guard; queue response backend field
├── main.py                       # EDIT: /api/open honors preference; /api/os/default-apps; unclean-exit banner
└── templates/
    ├── companion.html            # REWORK (R5/R7): live wizard with per-step verification
    ├── partials/autofill_status.html  # REWORK (R7/D2): path disclosure + fallback notice + mismatch line
    └── settings.html             # EDIT (R6): preferred-browser control

extension/
├── manifest.json                 # version stamped at stamp-time (R13); repo copy bumped at release
├── background/socket.js          # EDIT (R8): lastAttempt records incl. close codes; connect! handler
├── background/service-worker.js  # EDIT (R8): status? includes lastAttempt; connect!; fill-here refusal reason
└── popup/popup.js|popup.html     # EDIT (R8): state-specific text, Retry, non-dead Fill button

packaging/smoke_test.py           # EDIT (R12): pairing freshness/port/doctor gates
desktop.py                        # EDIT: lifecycle markers; freeze_support (R2)

tests/
├── test_inference.py             # NEW: hammer (max concurrency == 1), timeout, saturation
├── test_stamp_extension.py       # EXTEND: read-back verify, stamp_status, import allowlist (AST), manifest version
├── test_default_browser.py       # EXTEND: effective order w/ preference; open_url fallback
├── test_web.py / test_bridge_*.py# EXTEND: doctor endpoint, confirm_answer sentinel 200, banners
├── test_updates.py               # EXTEND: empty-download gate, locked-file deferral, prune
└── integration/test_pairing_e2e.py  # NEW (R12): stamp→load→connect→fill in real Edge AND Chrome
```

**Structure Decision**: single existing project; all business logic stays in
`engine/` (Principle IV). No schema migration — new state is settings keys +
small JSON files, chosen so the stamp path and doctor work even when the DB
layer is mid-init.

## Phase 0 → research.md

Thirteen decisions (R1–R13) recorded with rationale and rejected alternatives:
inference owner architecture; subprocess spike design + GO/NO-GO; lock-free
pending suggestions; dependency-free stamping; doctor endpoint + reject
counters; preferred-browser resolution + App Paths launch; fill-path
disclosure; popup diagnostics; unclean-exit marker; confirm-answer guard;
updater hardening; human-path E2E + frozen gates; manifest version stamping.

## Phase 1 → data-model.md, contracts/, quickstart.md

Entities/state: stamp status file, pairing record, companion session (+browser,
reject counters), inference request, browser preference + mismatch, lifecycle
marker, update artifact lifecycle. Contracts: engine inference API; HTTP
additions (doctor, os/default-apps, additive autofill fields); bridge protocol
additions (Hello.browser optional — protocol_v remains 1). Quickstart: manual
walkthrough for wizard (both browsers), fault injections, hammer, slow-draft
responsiveness, mismatch, updater sims, frozen smoke.

## Complexity Tracking

*No constitution violations — table intentionally empty.*
