# Implementation Plan: The Real Application

**Branch**: `021-the-real-application` | **Date**: 2026-08-02 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/021-the-real-application/spec.md`

## Summary

v2.0.0 met a real multi-section Workday application and returned **Filled 5 ·
Needs you 149 · Seen 156** — a review surface too crowded to read, most rows
carrying no question at all. Three separate defects compound into that number:
the panel de-duplicates rows by **element** rather than by question, it accepts
a whitespace label as a question and renders the row blank, and its per-session
index is never pruned, so every wizard step and every React remount accumulates
forever.

Behind those, the largest single share of the 149 is work-history and education
blocks — and the applicant's resume is **already parsed** into structured
`experience[]` and `education[]` entries that the fill layer has never read.

This feature makes the panel readable (one named row per question, grouped by
form section), teaches the fill layer to answer employment and education blocks
from that existing parsed history, captures the answers the applicant types so
each question is answered once ever, moves the panel wherever they want it, and
stops applicant-initiated AI work from failing silently or queueing behind
background scoring. It also turns on the fast AI tier that already ships and is
unreachable, and widens the profile and the job sources.

Nothing here changes what the automation clicks.

## Technical Context

**Language/Version**: Python 3.12 (engine + web), ES5-compatible browser JS
(extension content scripts — no build step)
**Primary Dependencies**: FastAPI, Jinja2, HTMX (vendored), SQLite,
llama-cpp-python 0.3.34 (bundled Qwen2.5-1.5B-Instruct-Q4_K_M +
EmbeddingGemma-300M GGUF), httpx, rapidfuzz, pydantic
**Storage**: SQLite at `data/jobs.db`; page reports at `data/reports/`; OS
credential vault for secrets
**Testing**: pytest (`-m browser` opt-in real-browser suite), PyInstaller
frozen smoke as CI gate
**Target Platform**: Windows 11 + macOS desktop app (PyWebView shell), MV3
Chrome/Edge companion extension
**Project Type**: Local-first desktop web app + browser companion
**Performance Goals** (measured on the applicant's i5-10210U, 4 cores):
on-device generation ~5–6 tok/s and prompt eval ~42 tok/s, both treated as
fixed; a tailoring request must either complete or report, never hang; a
panel render on a 150-field page must stay under one animation frame
**Constraints**: $0 recurring cost; works offline with no key; `engine/` never
imports `web/`; no JS framework or Node build step; `PROTOCOL_V` stays 1
(additive only); one on-device inference call at a time; secrets are
fill-and-forget
**Scale/Scope**: single user; 22,145 stored jobs; application pages up to ~150
fields across ~12 sections

## Constitution Check

*GATE: evaluated before Phase 0 and re-evaluated after Phase 1 design.*

| Principle | Verdict | Evidence |
|---|---|---|
| **I. Speed-to-Value First** | **PASS** | Every workstream removes a barrier between the applicant and a submitted application: a readable review list, blocks that fill themselves, questions answered once instead of every time. **No amendment needed** — this feature adds, removes and relaxes no click. Final Submit / Create account / pay stay the human's, CAPTCHA is untouched, LinkedIn stays zero-click; all pinned by the existing click-guard tests, which this feature extends rather than edits. |
| **II. Zero-Subscription Cost** | **PASS** | The cloud tier is Groq's free tier, already shipped and already documented in Settings — no card, no trial, and the app remains fully functional with no key and no network. New ingest sources are public JSON board endpoints with no key or a free key. No new paid dependency. |
| **III. API-First, Polite Ingestion** | **PASS** | Every new source is an official public JSON board endpoint routed through the existing `ingest/base.py`, inheriting its process-wide 1 req/sec per-domain limit and honest User-Agent. No scraping, no bot-protection bypass. A failing source cannot abort the others (FR-033). |
| **IV. Reusable Core, Thin Web Layer** | **PASS** | The two new engine modules (`history_answers`, `page_report`) are pure and import nothing from `web/`. The web layer gains read-only pages and one settings field. Enforced by the existing import-boundary test. |
| **V. Tested Core Logic** | **PASS** | Question de-duplication, section indexing, history selection, the observed-answer deny-list and the tier split are all deterministic and unit-tested first (TDD). The 150-field Workday fixture is built from a real capture, not imagined — Workstream A gates B and C precisely so the tests describe the real page. |

**Additional constraint check — secrets.** This feature introduces two new
places data could leak (page reports, learned answers) and therefore extends
`tests/test_secret_hygiene.py` in both directions rather than relying on the
existing coverage. A report records shape and never a value; a learned answer
is refused outright for any credential, self-ID, national identifier, date of
birth, government identifier or financial field.

**Re-check after Phase 1**: unchanged, all PASS. Design added no new
dependency, no new click, and no new engine→web import.

## Project Structure

### Documentation (this feature)

```text
specs/021-the-real-application/
├── plan.md              # This file
├── spec.md              # Feature specification (with Clarifications)
├── research.md          # Phase 0 — decisions and measurements
├── data-model.md        # Phase 1 — entities
├── quickstart.md        # Phase 1 — manual verification script
├── baseline.txt         # Recorded pre-change evidence
├── checklists/
│   └── requirements.md
├── contracts/
│   ├── page_report.md       # the shareable diagnostic
│   ├── section_context.md   # scanner → app section descriptor (additive)
│   └── observed_answer.md   # capture rules and deny-list
└── tasks.md             # Phase 2 output (/speckit.tasks)
```

### Source Code (repository root)

```text
engine/
├── autofill/
│   ├── field_core.py         # + observed outcome, section-aware decide
│   ├── history_answers.py    # NEW — employment/education from resume_sections
│   ├── page_answers.py       # question de-dupe, section grouping
│   ├── page_report.py        # NEW — value-free page snapshot
│   ├── ext_backend.py        # question fallback, entry pruning, observed routing
│   ├── answer_bank.py        # + record_observed / provenance rules
│   ├── profile_answers.py    # + new profile facts
│   ├── vocab.py              # + exp_* / edu_* tags
│   └── watcher.py            # SERIALIZE_JS parity with scanner.js
├── ingest/
│   ├── recruitee.py  teamtailor.py  personio.py  breezy.py  jazzhr.py   # NEW
│   └── adzuna.py  themuse.py                                            # NEW, optional key
├── matcher.py                # purpose-aware tier dispatch
├── local_llm.py              # streaming + token budgets
├── upgrade.py                # stand down for any interactive request
└── db.py                     # profile columns, report listing

extension/content/
├── scanner.js                # section context; label fallback
├── panel.js                  # drag + persist; grouped rendering
└── overlay.css               # drag affordance

web/
├── routes_api.py             # reports, learned answers, tier preference
└── templates/
    ├── learned_answers.html  # NEW
    ├── profile.html          # history editor + new fields
    ├── settings.html         # honest tier choice
    ├── diagnostics.html      # report list
    └── job_detail.html       # tailoring error handling

tests/
├── test_history_answers.py   test_observed_answers.py   test_page_report.py   # NEW
└── fixtures/ats_pages/workday_my_experience.html                              # NEW, from a real capture
```

**Structure Decision**: unchanged from 020 — a reusable `engine/` core, a thin
`web/` layer, and an MV3 companion whose serializer stays byte-parallel with
`engine/autofill/watcher.py`. Two new engine modules; no new top-level
directory; no build step introduced.

## Phase sequencing

**A (capture) strictly precedes B and C.** The existing Workday fixtures hold
9 and 2 fields, which is why this failure class was never caught. Writing B's
de-duplication rules against an imagined 150-field page would repeat exactly
the mistake this project has corrected three times by measurement. A produces
the real artefact; B and C are written against it.

**B precedes C.** History selection is indexed by form section, so section
grouping must exist and be trustworthy first.

D, E and F are independent of each other and of the A→B→C chain.

## Complexity Tracking

> No Constitution Check violations. Table intentionally empty.
