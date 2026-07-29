# Implementation Plan: The Truthful Fill

**Branch**: `017-truthful-fill` | **Date**: 2026-07-28 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/017-truthful-fill/spec.md`

## Summary

Apply Assist fills real applications but frequently fills the wrong thing:
it invents autobiographical facts, writes yes/no tokens into free-text
questions and paragraphs into dropdowns, regenerates the same answer a dozen
times until the app is unusable, and can attach something that is not the
applicant's résumé. This feature makes the fill **truthful and bounded** first
(refusal contract, prompt isolation, attempt caps, no regeneration loop,
always-reachable Stop), then makes it **shape-correct** (answer shape must fit
field shape; merged choice widgets; classifier repairs), then **better
supplied** (a real application profile plus a tag-keyed answer library), then
**better matched** (canonical synonym vocabulary, self-ID answered from stored
values, acknowledgements split by consequence), then **complete** (a verified
résumé attachment, on-page answer review with an ask-once-remember loop, and a
one-click entry point from a job).

Technical approach: three new pure engine modules (`profile_answers`, `vocab`,
plus a shape predicate in `field_core`), additive profile columns through the
existing migration list, additive bridge messages with `PROTOCOL_V` unchanged,
a service-worker file transport with content verification, and a panel that
becomes the review surface. No new runtime dependency and no new permission.

## Technical Context

**Language/Version**: Python 3.11+ (engine, web), ES2020 vanilla JS (MV3
extension, no build step)
**Primary Dependencies**: FastAPI + Jinja2 + vendored HTMX, SQLite, rapidfuzz,
pydantic, Playwright (fallback fill path), fpdf2 + PyMuPDF, llama-cpp (local
models). No new dependency is added by this feature.
**Storage**: SQLite at `data/jobs.db` — `user_profile` (single row, extended
additively), `answer_bank`, `application_answers`, `ai_drafts`, `jobs`
**Testing**: pytest (unit + contract), pytest markers `browser` / `slow`,
Playwright integration for the companion E2E, `packaging/smoke_test.py` for
the frozen build
**Target Platform**: Windows and macOS desktop app (PyInstaller), Chrome MV3
companion extension, local-only loopback HTTP + WebSocket
**Project Type**: local desktop web application with a paired browser extension
**Performance Goals**: bridge message handling stays non-blocking (no model
call on the message loop); at most one generation per unique question per job;
status view responsive with 90+ fields
**Constraints**: $0 recurring cost; offline-first; `engine/` never imports
`web/`; no JS framework and no Node build step; secrets never persisted or
logged; `PROTOCOL_V` stays 1 (additive only); the human performs every submit,
login and wizard advance
**Scale/Scope**: single user, one profile row; largest observed real form ~91
fields / ~30 distinct questions across two documents

## Constitution Check

*GATE: evaluated before Phase 0 and re-checked after Phase 1 design.*

| Principle | Assessment |
|---|---|
| **I — Speed-to-Value First** | PASS. Every workstream serves "complete and submit applications faster": the truthfulness work removes answers the applicant would otherwise have to find and delete by hand; the profile and library work removes repeated typing. No deferred capability (auth/multi-user, hosted deployment, CLI/MCP layer) is built. |
| **I — click clarifications** | PASS, unchanged. The badge launcher only sends a message to the local app; the panel's "Insert" writes a value the applicant typed into the field they chose — field-filling under the 011 clarification. Attaching the applicant's own file to a file input is likewise setting a field value; the Playwright path already does this. No new click class is introduced, so **no constitution amendment is required**. |
| **II — Zero-Subscription Cost** | PASS. No new dependency, service or API. Generation continues through the existing provider-agnostic tier dispatcher; this feature strictly *reduces* model calls. |
| **III — API-First, Polite Ingestion** | PASS. No ingestion change. The badge continues to read only the page the user is already viewing and to mutate nothing. |
| **IV — Reusable Core, Thin Web Layer** | PASS. All new logic lands in `engine/autofill/` as pure modules (`profile_answers.py`, `vocab.py`, predicates in `field_core.py`) with no web imports. `web/` changes are template and route-level only. Both fill backends consume the same decision core, so the Playwright path inherits every fix. |
| **V — Tested Core Logic** | PASS. Every defect becomes a failing test first (R24). Deterministic logic — classification, shape predicate, canonical matching, name layout, profile resolution — is unit-tested; generated output stays schema/contract-validated with a bounded retry, now capped explicitly (R2). |

**Result: no violations; Complexity Tracking is empty.**

One prior *specification* is superseded, deliberately and narrowly: feature
016's FR-013 ("self-identification questions are never AI-answered") becomes
"never AI-**generated**, answerable from the applicant's stored values" (D1,
R15). This is a spec-level change recorded in `spec.md` Assumptions, not a
constitution change.

## Project Structure

### Documentation (this feature)

```text
specs/017-truthful-fill/
├── spec.md              # Feature specification (FR-001..FR-046, SC-001..SC-011)
├── plan.md              # This file
├── research.md          # Phase 0 — R1..R24
├── data-model.md        # Phase 1 — entities, schema deltas, state machines
├── quickstart.md        # Phase 1 — how to run and verify the feature
├── contracts/
│   ├── bridge-protocol-additions.md   # additive messages and fields
│   ├── answer-resolution.md           # tag → value → shape contract
│   └── profile-schema.md              # profile fields and canonical values
├── checklists/
│   ├── requirements.md  # spec quality (complete)
│   └── truthfulness.md  # Phase 1 — the feature's own quality gate
└── tasks.md             # Phase 2 (/speckit.tasks)
```

### Source Code (repository root)

```text
engine/
├── autofill/
│   ├── profile_answers.py   # NEW — tag → profile value resolver (R12)
│   ├── vocab.py             # NEW — canonical values + synonym families (R14)
│   ├── field_core.py        # shape predicate, name_layout, decide() (R7, R10)
│   ├── fields.py            # classifier repairs + new tags, match_option (R10, R14)
│   ├── adapters.py          # ATS location remaps (R15 area)
│   ├── drafter.py           # caps, persistence, refusal reasons (R1..R4, R6)
│   ├── answer_bank.py       # refusal contract, prompt isolation (R4, R5)
│   ├── browser_controller.py# delegate to profile_answers; resume choice (R12, R18)
│   ├── ext_backend.py        # answers/apply_here/answer_question, no backoff reset (R1, R19)
│   ├── ext_protocol.py      # additive models (R19)
│   ├── watcher.py           # SERIALIZE_JS mirror of scanner changes (R8, R9)
│   └── drafts.py            # one row per (job, question) (R3)
├── db.py                    # additive user_profile columns (R11)
├── qa.py                    # profile facts fold into profile_answers (R12)
└── resume_pdf.py            # cover-letter PDF caching (FR-033)

extension/
├── background/service-worker.js  # rescan handler, fetch_file transport (R17, R21)
├── content/scanner.js            # nested de-dup, checkbox groups (R8, R9)
├── content/filler.js             # verified attach, filename (R17)
├── content/overlay.js            # panel rewrite, open root (R20)
├── content/discovery.js          # launcher button (R20)
└── content/main.js               # rescan, answer_question relay

web/
├── routes_api.py                 # profile fields, purge action (R11, R22)
├── routes_autofill.py            # answers feed, single-job start
├── templates/profile.html        # new profile sections
├── templates/job_detail.html     # Apply with Apply Assist (FR-040)
├── templates/practice_apply.html # Akuna-shaped fixture (R24)
└── templates/partials/autofill_status.html  # sticky controls, bounded list (R21)

tests/
├── test_profile_answers.py  test_vocab.py  test_field_shape.py   # NEW
├── test_fields.py  test_field_core.py  test_drafter.py  test_answer_bank.py
├── test_ext_backend.py  test_ext_protocol.py  test_extension_assets.py
├── test_browser_controller.py  test_watcher.py  test_db.py  test_web.py
└── integration/test_pairing_e2e.py  test_extension_fixture_pages.py
```

**Structure Decision**: unchanged from features 009–016 — a pure `engine/`
core, a thin `web/` layer, and a no-build-step MV3 extension. This feature adds
two engine modules and no new top-level directory. The two field serializers
(`extension/content/scanner.js` and `SERIALIZE_JS` in `watcher.py`) continue to
be changed in lockstep and are guarded by the existing parity test, which this
feature extends to cover the new de-duplication and grouping rules.

## Phase sequencing

Phases follow the spec's user-story priorities; each is independently
shippable and independently testable.

| Phase | Story | Delivers | Gate |
|---|---|---|---|
| Setup | — | branch, fixture scaffolding, failing-test harness | fixtures render |
| Foundational | — | shape predicate, `vocab`, `profile_answers` skeletons + their unit tests | new modules green, no behaviour change yet |
| P1 | US1 | no regeneration loop, caps, persistence, refusal contract, prompt isolation, sticky controls, purge | SC-002, SC-003, SC-004 |
| P2 | US2 | shape enforcement, serializer de-dup, checkbox groups, classifier repairs, name layout | SC-001 |
| P3 | US3 | profile columns + UI, resolver wiring, location family, library tags | SC-008 (partial) |
| P4 | US4 | canonical matching, self-ID answering, acknowledgement split | SC-008 |
| P5 | US5 | SW file transport, content verification, filename, tailored-only-if-tailored | SC-005, SC-011 |
| P6 | US6 | `answers` feed, panel rewrite, `rescan`, ask-once-remember | SC-006, SC-010 |
| P7 | US7 | job-detail entry point, badge launcher, review reconciliation | SC-007 |
| Polish | — | docs, frozen smoke, full battery ×2, ship | SC-009 + both installers verified |

## Risks and mitigations

| Risk | Mitigation |
|---|---|
| Serializer drift between `scanner.js` and `SERIALIZE_JS` — this feature changes both substantially | Extend the existing parity test to the de-dup and grouping rules *before* changing either; fix the known selector drift in the same pass (R10/C20). |
| Reversing 016's "never merge checkboxes" could regress radio handling | Merge logic is shared and tested per control type; per-member `checkbox` fills mean no wire change, so old companions are unaffected (R9). |
| Tighter refusal leaves the applicant with many manual fields | D7's ask-once-remember loop converts each refusal into a permanent library entry, so manual effort decays across applications (FR-045). |
| Stale tests pinned to removed behaviour (the recurring lesson from 015/016) | A dedicated sweep task rewrites every test that asserts the old drafting, EEO-refusal, resume-choice and status-panel behaviour, run before the phase that changes it. |
| Persisting drafts changes `ai_drafts` semantics while its production writer is unclear | R23: pin the current data source with a test before changing the review surface. |
| Larger profile increases the surface for a silent write failure (as `target_titles` already shows) | A single round-trip test asserts every `_PROFILE_COLUMNS` entry saves and reloads, which also fixes the latent bug. |

## Complexity Tracking

No constitution violations — this section is intentionally empty.
