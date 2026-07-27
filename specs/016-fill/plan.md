# Implementation Plan: The Fill Release

**Branch**: `016-fill` | **Date**: 2026-07-27 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/016-fill/spec.md`
**Design doc**: `docs/superpowers/specs/2026-07-27-feature-016-design.md`

## Summary

Make Apply Assist actually fill, on the page, by fixing the five verified
failure layers: (1) the bridge message loop blocks on inline LLM drafts and
batches fills until the whole form is decided — rebuild it as a decide-fast
loop with incremental fills plus a bounded background drafter that pushes
completed answers to the page (draft cache kills the infinite re-draft
loop); (2) choice fields are unanswerable — capture options and radio
groups, constrain drafting to the real options, fill radios/selects/
comboboxes honestly, never AI-answer sensitive questions; (3) the approval
gate never reached the page — remove it (fill-first, D2) with on-page
highlights and an on-page panel (D3), plus auto-opening the application
form via a strict apply-opener allowlist (D1, constitution v1.1.4);
(4) silent operational traps — watch transfer for new tabs, persisted
watches, surfaced errors, working re-scan, no Playwright preflight with a
live companion, discovery decongestion; (5) the tailor hard-crash — AI
subprocess isolation becomes the default, with explicit generation bounds
and load hygiene. The proven fill core (scanner/filler mechanics,
click-guards, pairing layer) is extended, not replaced.

## Technical Context

**Language/Version**: Python 3.11+ (engine + FastAPI web), vanilla ES
modules (MV3 extension) — no build step
**Primary Dependencies**: existing only — FastAPI/Starlette, Jinja2 + HTMX
(vendored), llama-cpp-python (bundled models), Playwright channels,
pydantic (bridge validation); NEW code uses stdlib only
**Storage**: SQLite `jobs.db` — additive columns on the answer bank
(origin ai/human, job scope) via the existing lightweight migration
pattern; `chrome.storage.session` for the extension's watched-tab set;
no new files
**Testing**: pytest (default suite now runs with AI isolation ON),
`-m browser` real-browser integration (extended fixture: apply-opener,
new-tab, radio/combobox, submit click log; serializer parity),
`-m slow` offline gates, `packaging/smoke_test.py` frozen gate (extended:
subprocess default + tailor call)
**Target Platform**: Windows 11 primary, macOS via CI dmg job; engine stays
cross-platform importable (Linux CI)
**Project Type**: local desktop web app (FastAPI + pywebview shell) +
unpacked MV3 browser extension companion
**Performance Goals**: known fields dispatched < 2 s from form detection
(SC-002); companion status staleness < 5 s throughout, including during
drafts (FR-001/SC-002); at most one draft per unique question per session
(SC-003); bridge `fields` handler contains no model call
**Constraints**: $0 / offline-first / no new third-party deps / engine
never imports web / never auto-submit (v1.1.4 permits form-OPENING clicks
only) / secrets fill-and-forget / no JS framework / PROTOCOL_V stays 1
(additive messages + fields only)
**Scale/Scope**: 1 new engine module (`autofill/drafter.py`), ~9 engine
modules edited, 3 web route modules + 4 templates edited, 1 new extension
content module (`opener.js`) + 7 extension files edited, 1 small additive
DB migration, ~12 test files new/extended, 1 fixture page extended

## Constitution Check

*GATE: evaluated against constitution v1.1.4 — PASS (no violations; table
not needed).*

- **I. Speed-to-Value**: directly serves "complete and submit applications
  faster" — v1.5.0 pairing works but filling does not; this is the payoff
  release. No deferred capability (auth/hosting/CLI-MCP) is touched.
- **Automation rules (III clarifications)**: the apply-opener relies on the
  NEW v1.1.4 clarification (form-opening clicks via strict per-ATS
  allowlist, never type=submit, one-shot); the 011 fill-path click rule is
  unchanged — `click_guard` still denies "apply" during filling; every
  submitting/advancing/authenticating control stays human-only and the E2E
  suite asserts zero such clicks (SC-004). Sensitive questions are never
  AI-answered (FR-013).
- **II. Zero-Subscription Cost**: all new code is stdlib; no new services;
  the companion stays an unpacked extension.
- **III. Polite Ingestion**: no ingestion changes; discovery traffic is
  REDUCED (per-page score cache).
- **IV. Reusable Core, Thin Web Layer**: the drafter, grouping, constrained
  drafting, ledger, caches, and bounds all live in `engine/`; `web/` only
  composes (activity log fields, doctor counters, tailor states). Engine
  imports no web module.
- **V. Tested Core Logic**: TDD throughout — drafter cache/backoff hammer,
  bridge-responsiveness regression, grouping + parity, constrained-draft
  validation, sensitive allowlist, ledger retryability, version gate,
  fault containment on the default path, plus the extended real-browser
  E2E and frozen gates.

*Post-Phase-1 re-check: still PASS — no new dependencies or layer
violations introduced by the design artifacts.*

## Project Structure

### Documentation (this feature)

```text
specs/016-fill/
├── plan.md              # This file
├── research.md          # Phase 0: decisions R1–R14 with rationale
├── data-model.md        # Phase 1: entities, columns, caches, schemas
├── quickstart.md        # Phase 1: manual verification walkthrough
├── contracts/
│   ├── bridge-protocol-additions.md  # rescan/scan_error/child_tab, Descriptor.members, FillItem.kind radio (protocol_v stays 1)
│   ├── drafter-api.md                # engine-internal drafting contract (cache, backoff, sensitive policy, auto-save scope)
│   └── http-api-additions.md         # activity log fields, doctor counters, tailor states, confirm=bank-only
└── tasks.md             # Phase 2 (/speckit.tasks — not created by plan)
```

### Source Code (repository root)

```text
engine/
├── inference.py                  # EDIT (R12): JOBS_AI_SUBPROCESS defaults ON ("0" opts out)
├── local_llm.py                  # EDIT (R13): max_tokens carried per purpose
├── semantic.py                   # EDIT (R13): _load_attempted guard; embedder n_batch cap
├── tailor.py                     # EDIT (R13): prompt ≤ safe band, timeout_s≈300, 1 local attempt
├── qa.py                         # EDIT (R7): draft() receives type/options/maxlength; option-constrained prompt
├── db.py                         # EDIT (R5, R11): H1B employer in-memory cache; answer-bank origin/job-scope columns
└── autofill/
    ├── drafter.py                # NEW (R2): bounded background drafter — cache, negative cache, push
    ├── ext_backend.py            # EDIT (R1,R3,R4,R8): decide-fast, incremental fills, _inflight TTL,
    │                             #   real outcomes, watch transfer, version gate, dropped/scan_error counters
    ├── ext_protocol.py           # EDIT (R6): additive messages/fields (rescan, scan_error, child_tab, members, required, kind radio)
    ├── browser_controller.py     # EDIT (R11): park gate → drafting list; rescan() nudges in ext mode; preflight skip
    ├── field_core.py             # EDIT (R3,R6): cache-version retryability; grouped-field decisions
    ├── answer_bank.py            # EDIT (R7): descriptor-aware suggest, sensitive allowlist, scoped auto-save
    ├── watcher.py                # EDIT (R6,R8): serializer grouping (parity), radio fill branch
    └── adapters.py               # EDIT (R9): per-ATS apply-opener selectors

web/
├── routes_bridge.py              # EDIT: doctor gains dropped-fields/scan-error counters
├── routes_autofill.py            # EDIT (R1,R11): preflight skip w/ live companion; confirm endpoints bank-only; activity log
├── routes_api.py                 # EDIT (R13): tailor timeout/attempt + clean failure payload
└── templates/
    ├── partials/autofill_status.html  # REWORK (R11): activity log + drafting list (gate removed)
    ├── autofill.html             # EDIT (R11): passive log presentation
    ├── job_detail.html           # EDIT (R13): tailor progress + failure rendering
    └── practice_apply.html       # EDIT (R14): radio group, custom combobox, maxlength field

extension/
├── content/opener.js             # NEW (R9): apply-opener allowlist + one-shot click (queue-driven watches only)
├── content/scanner.js            # EDIT (R6): radio grouping, required, group labels
├── content/filler.js             # EDIT (R8,R10): radio branch, normalized select match, wider combobox harvest,
│                                 #   honest outcomes, ai_draft/needs-you highlights
├── content/main.js               # EDIT (R9,R10): opener hook, rescan handler, scan_error report, panel wiring
├── content/overlay.js            # REWORK (R10): on-page panel (status, counters, field list, Fill again)
├── content/discovery.js          # EDIT (R5): per-page score cache
├── background/service-worker.js  # EDIT (R4): error surfacing, tabs.onCreated transfer, storage.session watches
├── background/tabs.js            # EDIT (R4): open ack/retry, watch persistence
└── popup/popup.js                # EDIT: busy reason display

packaging/smoke_test.py           # EDIT (R14): runs with default isolation; tailor smoke call
desktop.py                        # (freeze_support already present from 015)

tests/
├── test_drafter.py               # NEW: cache/one-draft hammer, backoff, sensitive allowlist, push callback
├── test_ext_backend.py           # EXTEND: incremental fills, TTL, transfer, version gate, counters, no-LLM-in-handler
├── test_field_core.py            # EXTEND: retryable-on-new-answer, grouped decisions
├── test_answer_bank.py           # EXTEND: constrained suggest, scoped auto-save, sensitive refusal
├── test_browser_controller.py    # SWEEP (R11): park-gate tests rewritten to drafting-list model
├── test_routes_autofill.py       # SWEEP (R11): confirm=bank-only, activity log, preflight skip
├── test_web.py                   # SWEEP (R11): pending-panel asserts → activity log asserts
├── test_inference.py             # EXTEND (R12): default-ON semantics, opt-out env
├── test_tailor.py                # NEW/EXTEND (R13): prompt cap, timeout, bounded attempts, persist
├── test_extension_assets.py      # EXTEND: opener allowlist parity, panel presence, popup busy case
└── integration/test_pairing_e2e.py  # EXTEND (R14): apply-opener fixture, new-tab transfer, choice fills,
                                  #   zero-submit assertion, serializer parity
```

**Structure Decision**: single existing project; all decision logic stays
in `engine/` (Principle IV). One additive DB migration (answer-bank
columns) via the established `ALTER TABLE` guard pattern; everything else
is settings/env/in-memory/session storage.

## Phase 0 → research.md

Fourteen decisions (R1–R14) recorded with rationale and rejected
alternatives: decide-fast loop + incremental fills; drafter design (cache
key, backoff, push-via-rescan); ledger retryability + inflight TTL; watch
transfer + persistence + open ack; discovery decongestion; radio grouping
model; option-constrained drafting + sensitive policy; filler upgrades +
version gate; apply-opener allowlist; on-page panel + highlights + Fill
again; approval-gate removal + blast radius; subprocess default ON;
generation bounds + load hygiene + tailor UX; verification harness.

## Phase 1 → data-model.md, contracts/, quickstart.md

Entities/state: logical field (grouped descriptor), draft record, watch
target, field outcome (cache-versioned), on-page annotation, AI runtime
status, employer cache, answer-bank origin/scope columns, activity log
entry. Contracts: bridge protocol additions (all additive, protocol_v 1);
engine drafter API; HTTP additions. Quickstart: manual walkthrough — both
browsers, apply-opener, slow-draft responsiveness, choice fields, sensitive
flagging, Fill again, tailor with isolation, induced fault, frozen smoke.

## Complexity Tracking

*No constitution violations — table intentionally empty.*
