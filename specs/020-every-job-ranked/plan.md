# Implementation Plan: Every Job Ranked

**Branch**: `020-every-job-ranked` | **Date**: 2026-08-01 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/020-every-job-ranked/spec.md`

## Summary

Two-thirds of the applicant's eligible feed has no score, because the scoring
stage spends ~67 s of on-device inference per job, runs inline inside the
refresh run, and gets superseded and restarted before it can finish. This
feature splits scoring into a **model-free ranking stage** that covers every
eligible job during the refresh (measured: 0.0044 s/job — the whole 627-job
backlog in under 3 s) and a **background assessment pass** that upgrades the
best candidates to full AI analysis, ordered by the semantic pre-ranking that
already exists. The refresh then finishes in seconds instead of hours, alerts
stop queueing behind inference, and duplicate concurrent passes become
impossible.

Riding along: rich-text cover letters (today invisible to the scanner, the
worst class of gap this project recognises), the companion's per-page idle
cost, an expression index for the feed listing, and iCIMS advance selectors.

Nothing here changes what the automation clicks.

## Technical Context

**Language/Version**: Python 3.12 (engine + web), ES5-compatible browser JS
(extension content scripts — no build step)
**Primary Dependencies**: FastAPI, Jinja2, HTMX (vendored), SQLite,
llama-cpp-python (bundled Qwen2.5-1.5B + EmbeddingGemma-300M GGUF), rapidfuzz
**Storage**: SQLite at `data/jobs.db`; OS credential vault for secrets
**Testing**: pytest (`-m browser` opt-in real-browser suite), PyInstaller
frozen smoke as CI gate
**Target Platform**: Windows 11 + macOS desktop app (PyWebView shell), MV3
Chrome/Edge companion extension
**Project Type**: Local-first desktop web app + browser companion
**Performance Goals** (measured on the applicant's i5-10210U, 4 cores):
ranking the full eligible backlog < 30 s with zero inference; refresh run
reaching `finished` < 60 s; one AI assessment ≈ 67 s (treated as fixed);
generated application answers keep their existing budget under background load
**Constraints**: $0 recurring cost; offline-capable; `engine/` never imports
`web/`; no JS framework or Node build step; `PROTOCOL_V` stays 1 (additive
only); one on-device inference call at a time
**Scale/Scope**: single user; 22,145 stored jobs, 937 currently eligible

## Constitution Check

*GATE: evaluated before Phase 0 and re-evaluated after Phase 1 design.*

| Principle | Verdict | Evidence |
|---|---|---|
| **I. Speed-to-Value First** | **PASS** | Directly ranks applyable jobs sooner: the feed goes from 33% to 100% ranked, and the refresh stops blocking itself for hours. No speculative abstraction — the one new module replaces an inline loop. **No amendment needed**: this feature adds, removes, and relaxes no click. The 019 progression-click clarification and every prohibition under it (final submit, Create account, pay, CAPTCHA, LinkedIn) stand unchanged, pinned by FR-024 and by the existing click-guard tests. |
| **II. Zero-Subscription Cost** | **PASS** | No new dependency, service, model, or API. The ranking tier is `engine/basic_match.py`, already in the repo. Work is *removed* from the paid-by-CPU tier, not added. |
| **III. API-First, Polite Ingestion** | **PASS** | Ingestion is untouched. The liveness check keeps its existing per-domain rate limit and simply stops queueing behind inference. |
| **IV. Reusable Core, Thin Web Layer** | **PASS** | `engine/upgrade.py` is pure Python and imports nothing from `web/`. The web layer gains a read-only progress field on an existing status endpoint plus a template badge. Enforced by the existing import-boundary test. |
| **V. Tested Core Logic** | **PASS** | Ranking, pass bookkeeping, and the fill-session stand-down are deterministic and unit-tested first (TDD). Assessment output stays pydantic-validated with the existing bounded retry, and — as Principle V requires — an unscored job must still appear in the feed, which is exactly what FR-002 strengthens. |

**Re-check after Phase 1**: unchanged, all PASS. The design added no new
dependency and no new click; the single new module stayed inside `engine/`.

**Complexity Tracking**: not required — no violations.

## Project Structure

### Documentation (this feature)

```text
specs/020-every-job-ranked/
├── plan.md              # This file
├── spec.md              # Feature specification
├── research.md          # Phase 0 — measured decisions
├── data-model.md        # Phase 1 — entities and state
├── quickstart.md        # Phase 1 — manual verification
├── contracts/
│   ├── scoring-tiers.md     # ranking vs assessment contract
│   ├── upgrade-api.md       # engine/upgrade.py public surface
│   └── richtext-fill.md     # contenteditable scan + write contract
├── checklists/
│   └── requirements.md  # spec quality gate
└── tasks.md             # Phase 2 output (/speckit.tasks)
```

### Source Code (repository root)

```text
engine/
├── pipeline.py          # CHANGED: _score_new_jobs splits into _rank_new_jobs
│                        #   (inline, uncapped, model-free) + a start of the
│                        #   background pass; _post_ingest reordered
├── upgrade.py           # NEW: single-flight, resumable AI assessment pass
├── basic_match.py       # REUSED unchanged — the ranking tier
├── semantic.py          # REUSED unchanged — order_jobs picks upgrade order
├── matcher.py           # REUSED unchanged — analyze_match does assessment
├── inference.py         # REUSED unchanged — single-owner AI worker
├── db.py                # CHANGED: assessment-progress record, feed expression
│                        #   index migration, jobs_needing_score reuse
└── autofill/
    ├── adapters.py      # CHANGED: iCIMS ADVANCE_ALLOWLIST entries
    ├── watcher.py       # CHANGED: SERIALIZE_JS parity for rich-text
    ├── fields.py        # CHANGED: rich-text classification inputs
    ├── field_core.py    # CHANGED: rich-text value read / decide
    └── browser_controller.py  # CHANGED: public live-session predicate

extension/content/
├── scanner.js           # CHANGED: rich-text in FIELD_SELECTOR, value read
├── filler.js            # CHANGED: rich-text write path
└── discovery.js         # CHANGED: idle backoff for the periodic probe

web/
├── routes_api.py        # CHANGED: assessment progress on the status payload
└── templates/feed.html  # CHANGED: score-kind badge + assessment progress

tests/
├── test_upgrade.py            # NEW: pass bookkeeping, single-flight, resume
├── test_pipeline.py           # CHANGED: ranking coverage, ordering, lifecycle
├── test_inference.py          # CHANGED: fairness / no-starvation
├── test_field_core.py         # CHANGED: rich-text decisions
├── test_extension_assets.py   # CHANGED: parity + selector pins
├── integration/
│   ├── test_autofill_fixture_pages.py  # CHANGED: rich-text fill
│   └── test_escort_journeys.py         # CHANGED: iCIMS advance
└── fixtures/ats_pages/        # NEW: richtext_cover_letter.html,
                               #      lever_richtext.html, icims_step.html
```

**Structure Decision**: The existing layout is kept exactly. The only new
engine module is `engine/upgrade.py`, which owns the background pass; every
other change is an edit to a file that already owns that concern. No new
package, no new layer — the ranking tier, the semantic ordering, the tier
dispatcher, and the inference worker all already exist and are reused rather
than rebuilt.

## Phasing

1. **Foundational** — the tier split and the run lifecycle (US1 + US2). These
   are the reported defect; everything else is additive on top.
2. **Fairness** (US3) — must land with, not after, the background pass, since
   the pass is what creates the starvation risk.
3. **Rich text** (US4) — independent of the scoring work; touches the
   companion and the fill decision path only.
4. **Idle cost** (US5) — begins with a measurement task, per this project's
   "measure, don't guess" rule.
5. **Reach** (US6) — feed index and iCIMS selectors; contained, low-risk.
6. **Docs + ship** — `docs/USER_MANUAL.md:81`'s "a few minutes" becomes true,
   `WHATS_NEW["2.0.0"]`, frozen smoke, both installers verified.

## Verification

Full unit battery ×2 → `-m browser` → `tests/test_secret_hygiene.py` →
frozen smoke → the real-data check in [quickstart.md](./quickstart.md) against
the applicant's own 937-job database → manual Workday/Greenhouse/LinkedIn
passes including 019's outstanding T076 → tag `v2.0.0` → verify both
installers by magic bytes and SHA-256 against the release body.

Ship as a **major** version: `MAX_SCORE_PER_RUN` changes meaning and most
scores become quick-tier, which is a visible behaviour change.
