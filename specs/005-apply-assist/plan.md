# Implementation Plan: Apply Assist

**Branch**: `005-apply-assist` | **Date**: 2026-07-20 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/005-apply-assist/spec.md`

## Summary

Bundle a local, offline AI model into the installer as a new scoring/drafting
tier (cloud key → local model → deterministic basic match), and add an
app-driven "Apply Assist" flow that opens each shortlisted job's real
application page in a dedicated, isolated headed browser profile, autofills
recognized fields from the user's profile and a reusable answer bank, and
never performs the final submit or login click itself — the human always
does. Unrecognized or legally-sensitive questions (work authorization,
sponsorship) always pause for explicit user confirmation before being saved
or used. Saved per-domain logins live in the OS keychain and are filled but
never auto-submitted. The user explicitly advances the queue via a "Done,
next application" control. A bug-sweep pass over the existing shipped app
(v0.4.2) runs first to establish a clean baseline.

## Technical Context

**Language/Version**: Python 3.11+ (unchanged from features 001-004)
**Primary Dependencies**: New — `llama-cpp-python` (local LLM inference),
`playwright` (headed browser automation), `keyring` (OS-keychain credential
storage). Existing, reused as-is — FastAPI, Jinja2 + HTMX, `httpx`,
`openai` (cloud LLM client shape), `rapidfuzz` (fuzzy question matching),
`pydantic`, PyInstaller/Inno Setup/dmg packaging.
**Storage**: SQLite (`engine/db.py`, existing) gains `answer_bank` and
`application_answers` tables plus a couple of `user_profile` columns; the
bundled model file and downloaded Chromium binary live under the existing
per-OS `paths.data_dir()`; credential *secrets* live only in the OS keychain
(Windows Credential Manager / macOS Keychain via `keyring`), never in SQLite.
**Testing**: pytest (existing). New: fixture-dict tests for the field
classifier and answer-bank matching (no real browser needed), mocked
`Llama`/`OpenAI` for LLM-tier dispatch tests, mocked Playwright for queue
advance/session-state logic, a `keyring` in-memory test backend for
credential save/get/delete.
**Target Platform**: Windows 10+ and macOS desktop installers (existing
PyInstaller/Inno Setup/dmg pipeline, GitHub Actions CI on `v*` tags).
**Project Type**: Desktop app — FastAPI+Jinja2+HTMX web layer served locally,
packaged as a native installer (existing `engine/`+`web/` structure; no new
project type introduced).
**Performance Goals**: Local LLM must return a short drafted answer/score in
a few seconds on typical consumer CPU hardware (not real-time chat — one-shot
per-question/per-job drafting, throttled the same way cloud calls already
are). One-time Chromium download on first Apply Assist use is a one-off
cost, not a per-session one.
**Constraints**: Local AI and browser automation MUST work fully offline
(FR-001) except for the one-time Chromium download; MUST remain $0 recurring
cost (Principle II); native-dependency bundling (llama-cpp-python's compiled
core, Playwright's driver files) MUST be verified via a real, executed
inference/launch in `packaging/smoke_test.py` — not an import check — per
the v0.4.0 tls_client incident (`specs/004-get-hired/patch-0.4.1.md`); the
app MUST NEVER click a final submit or login button (FR-008, FR-016) and
MUST NEVER attempt to bypass a site's bot protection (FR-019, Principle III).
**Scale/Scope**: Single user, single machine — unchanged from prior features.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

Checked against constitution v1.1.0 (amended this session to permit local
LLM + Playwright for this feature — see commit `2724635`):

- **I. Speed-to-Value First** — PASS. Every workstream maps directly to
  "get hired faster": local AI removes the setup friction that blocks
  quality scoring for new users; Apply Assist removes the repetitive-typing
  bottleneck in actually applying. Local LLM and Playwright are no longer on
  the deferred list (constitution v1.1.0). Auth/multi-user, hosted
  deployment, and a CLI/MCP layer remain out of scope and are not touched.
- **II. Zero-Subscription Cost** — PASS. `llama-cpp-python`, the bundled
  model (Apache 2.0), `playwright`, and `keyring` are all free/OSS with no
  recurring cost; Chromium download is free. Installer size grows
  substantially (~1GB+) — an explicit, accepted tradeoff (spec Assumptions),
  not a cost violation.
- **III. API-First, Polite Ingestion** — PASS (mostly N/A — this feature
  doesn't ingest job listings). The one applicable rule — never bypass bot
  protection — is directly encoded as FR-019 and the Workday/graceful-
  fallback behavior (edge cases), not worked around.
- **IV. Reusable Core, Thin Web Layer** — PASS. All new logic
  (`engine/local_llm.py`, `engine/autofill/fields.py`,
  `engine/autofill/answer_bank.py`, `engine/autofill/browser_controller.py`,
  `engine/credentials.py`) lives in `engine/`, pure Python, no FastAPI
  imports. `web/routes_autofill.py` stays thin (routes + templates only),
  matching the existing `web/routes_api.py` pattern.
- **V. Tested Core Logic** — PASS (planned). Field classifier and answer-bank
  matching are fully unit-testable against literal fixture dicts, no browser
  required. LLM-tier dispatch and browser-queue advance logic are tested
  with mocks. See `tasks.md` (Phase 2) for the concrete task list.

No violations requiring Complexity Tracking.

**Post-Phase-1 re-check**: Design artifacts (`research.md`, `data-model.md`,
`contracts/http-api.md`, `quickstart.md`) introduce no new dependency,
module, or data flow beyond what this Constitution Check already covers —
`engine/autofill/` stays pure logic, `web/routes_autofill.py` stays thin,
`answer_bank`/`application_answers` are ordinary SQLite tables via the
existing migration idiom, and the credential/model/browser resources that
live outside SQLite are documented as such rather than smuggled into the
DB layer. Gate still PASSES.

## Project Structure

### Documentation (this feature)

```text
specs/005-apply-assist/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/
│   └── http-api.md      # Phase 1 output — new routes only, additive to 001's contract
└── tasks.md             # Phase 2 output (/speckit.tasks — not created here)
```

### Source Code (repository root)

```text
engine/
├── local_llm.py                 # NEW — bundled local model, peer to basic_match.py
├── matcher.py                   # MODIFIED — _chat becomes a tier dispatcher
├── pipeline.py                  # MODIFIED — three-way scoring tier branch
├── db.py                        # MODIFIED — answer_bank, application_answers tables;
│                                 #   user_profile sponsorship/visa columns
├── credentials.py                # NEW — keyring-backed per-domain credential vault
└── autofill/                     # NEW package
    ├── __init__.py
    ├── fields.py                 # pure field-taxonomy classifier (fixture-testable)
    ├── answer_bank.py             # lookup/save/suggest, reuses matcher._chat tiers
    ├── browser_controller.py      # Playwright lifecycle, dedicated bg thread, queue
    └── browser_setup.py           # first-use Chromium install (subprocess + progress)

web/
├── routes_autofill.py            # NEW — thin routes: queue, next, status, page
└── templates/
    └── autofill.html              # NEW — Apply Assist page (queue status, Done/Next,
                                    #   answer-bank review/confirm UI)

packaging/
├── jobengine.spec                # MODIFIED — llama_cpp + playwright native-lib bundling,
│                                 #   model .gguf as datas, build-time assertions
├── fetch_model.py                 # NEW — CI/local build step: download+verify pinned model
└── smoke_test.py                  # MODIFIED — local-llm-selftest + Chromium-launch routes

tests/
├── test_local_llm.py              # NEW
├── test_fields.py                 # NEW
├── test_answer_bank.py            # NEW
├── test_credentials.py            # NEW
└── test_browser_controller.py     # NEW (Playwright mocked)
```

**Structure Decision**: Single project, extending the existing `engine/` +
`web/` + `packaging/` layout from features 001-004 — no new top-level
project or split is introduced. New logic is isolated under `engine/autofill/`
as its own package (per Constitution IV) rather than mixed into existing
modules, since it's a genuinely distinct capability (browser automation)
from the existing ingestion/scoring/pipeline code.

## Complexity Tracking

*No Constitution Check violations — this section intentionally left empty.*
