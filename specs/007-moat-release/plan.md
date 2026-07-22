# Implementation Plan: The Moat Release

**Branch**: `007-moat-release` | **Date**: 2026-07-21 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/007-moat-release/spec.md`

## Summary

Deepen all four differentiating pillars in one release (v0.7.0): Apply
Assist gains resume-file attachment, multi-page fill, a per-field fill
report, structured-input answering, and queue recovery; sponsorship gains
wage/denial data, local A–F grades, cap-exempt detection, and a
strong-sponsors filter; a Resume builder turns the uploaded resume into
editable structured sections rendered as per-job tailored ATS-safe PDFs
(fpdf2); and the whole UI is redesigned as "Instrument, evolved" — full
token system, light "datasheet" default + dark "scope" alternate, grouped
nav, toasts, poll-clobber fix, kanban pipeline, mission-control Apply
Assist panel, onboarding checklist, accessibility pass. Constitution rules
(never auto-submit/auto-login, $0, local-first) bind throughout. Technical
decisions: [research.md](research.md); entities: [data-model.md](data-model.md);
endpoint contracts: [contracts/http-api.md](contracts/http-api.md);
verification walkthrough: [quickstart.md](quickstart.md).

## Technical Context

**Language/Version**: Python 3.12 (dev venv; CI pins 3.12)
**Primary Dependencies**: FastAPI + Jinja2 + HTMX (vendored), Playwright
(chromium, headed, existing), llama-cpp-python + bundled Qwen2.5-1.5B
(existing), keyring (existing), pandas (existing, USCIS/DOL loading),
**fpdf2 (new, pinned)** + bundled DejaVu TTFs (new data files)
**Storage**: SQLite at `data/jobs.db` (existing; additive `_MIGRATIONS`
columns), filesystem under `paths.data_dir()` for resume + tailored PDFs
**Testing**: pytest (300 passing at branch point; TDD per task)
**Target Platform**: Windows + macOS desktop (PyInstaller frozen + dev)
**Project Type**: web-app-in-desktop-shell (existing architecture)
**Performance Goals**: PDF render < 1s; fill pass per page < 5s on a
normal form; no UI action without feedback within 1s (SC-004)
**Constraints**: $0 recurring; offline-capable except ingestion/cloud
scoring; no Node build step; never auto-submit/auto-login/bypass bot
protection; engine/ never imports web/
**Scale/Scope**: single user, ~10k job rows, ~28k employer records; 7
pages redesigned; ~5 new engine modules

## Constitution Check

*GATE: evaluated against constitution v1.1.0 — PASS (pre-design and
re-checked post-design).*

- **I. Speed-to-Value**: every pillar directly serves "complete and
  submit applications faster" (resume attachment, multi-page fill,
  tailored PDFs) or "rank them better" (grades, strong-sponsors filter).
  No deferred capability (auth/multi-user, hosted, CLI/MCP) is touched.
  Local LLM + Playwright already permitted (005 amendment). ✅
- **II. Zero cost**: fpdf2 (LGPL) + DejaVu fonts (free license) are the
  only additions; no paid services. ✅
- **III. Polite ingestion**: no new ingestion sources; multi-page fill
  never bypasses bot protection and the human performs every navigation/
  submit/login click (FR-004 restates; tests assert). ✅
- **IV. Reusable core, thin web**: new logic lands in `engine/`
  (`resume_extract.py`, `resume_pdf.py`, sponsorship extensions,
  autofill controller changes); `web/` gains thin routes + templates
  only. Single-profile assumptions stay additive. ✅
- **V. Tested core**: grade formula, cap-exempt classifier, extraction
  schema validation, fill idempotency, masking, and PDF determinism all
  get pytest-first coverage; LLM outputs schema-validated with bounded
  retry (existing idiom). ✅

No violations → Complexity Tracking not required.

## Project Structure

### Documentation (this feature)

```text
specs/007-moat-release/
├── plan.md              # This file
├── research.md          # Phase 0 — technical decisions
├── data-model.md        # Phase 1 — schema + JSON shapes + invariants
├── quickstart.md        # Phase 1 — live verification walkthrough
├── contracts/
│   └── http-api.md      # Phase 1 — endpoint contracts
├── checklists/
│   └── requirements.md  # spec quality checklist (complete)
└── tasks.md             # Phase 2 (/speckit.tasks — not created here)
```

### Source Code (repository root)

```text
engine/
├── db.py                    # _MIGRATIONS: user_profile/companies/h1b_employers columns
├── resume_extract.py        # NEW — ResumeSections schema + LLM extraction (matcher._chat)
├── resume_pdf.py            # NEW — fpdf2 rendering: resume + cover letter, fingerprint cache
├── sponsorship.py           # wage/denial capture, grade formula, cap_exempt heuristic
├── tailor.py                # unchanged output; consumed by resume_pdf
└── autofill/
    ├── browser_controller.py  # file attach, page-change rescan, fill report, queue recovery
    ├── browser_setup.py       # unchanged
    ├── fields.py              # option-matching support for select/radio/checkbox
    └── answer_bank.py         # unchanged

web/
├── main.py                  # theme stamping, onboarding context, board view context
├── routes_api.py            # resume-sections PUT, reextract, PDFs, strong_sponsors, theme
├── routes_autofill.py       # rescan, resume-queue, extended status
├── static/
│   ├── styles.css           # rebuilt: full token system, light+dark, all components
│   ├── app.js               # NEW — toasts, polling gate, kanban DnD, theme toggle
│   └── fonts/               # NEW — DejaVu TTFs (bundled, spec datas entry)
└── templates/               # all pages restyled; new partials:
    ├── partials/resume_builder.html
    ├── partials/pipeline_board.html
    ├── partials/autofill_status.html   # mission-control rebuild
    └── partials/onboarding.html

packaging/
├── jobengine.spec           # fpdf2 hiddenimports if needed; fonts datas + assertion
└── smoke_test.py            # + /api/diagnostics/pdf-selftest check

tests/                       # new: test_resume_extract, test_resume_pdf,
                             # test_sponsor_grade; extended: test_fields,
                             # test_browser_controller, test_sponsorship,
                             # test_api, test_routes_autofill, test_settings
```

**Structure Decision**: existing two-package architecture (engine/ core,
web/ thin layer) extended in place — no new top-level packages; all new
business logic is engine-side per Principle IV.

## Implementation order (feeds /speckit.tasks)

1. **WS-4a Design-system foundation**: tokens, both themes, `app.js`
   (toast + polling gate), styled `.feed-table`, nav groups/active state,
   theme setting + head stamping. Fixes poll-clobber (FR-024) first since
   every later UI task builds on it.
2. **WS-3 Resume builder + PDFs**: db columns → `resume_extract.py` →
   builder UI (keep-vs-re-extract flow) → `resume_pdf.py` + download
   routes + pdf-selftest diagnostic.
3. **WS-1 Apply Assist depth**: store original file → `set_input_files`
   attach (tailored-preferred) → fields.py option matching → fill report
   (masked credentials) → page-change rescan + manual rescan route →
   interruption/resume → batch summary → mission-control panel (lands on
   WS-4a styles).
4. **WS-2 Sponsorship intelligence**: loader extensions (wage/denials) →
   grade formula + cap-exempt heuristic (pure, tested) → apply_to_companies
   recompute → feed/detail badges + evidence panel + strong_sponsors filter.
5. **WS-4b Redesign completion**: kanban board (drag + buttons), onboarding
   checklist, accessibility pass (labels, aria-live, contrast), resume
   drop zone.
6. **Ship**: docs (USER_MANUAL/USER_GUIDE), APP_VERSION → 0.7.0, packaging
   spec fonts assertion, full suite ×2, quickstart walkthrough live,
   frozen smoke test, tag v0.7.0, both installers verified on the Release.

**Pre-gate (outside this feature)**: v0.6.1 must ship first — root-cause
and fix the mac-dmg pytest failure from the v0.6.0 tag (tracked as its own
patch, not a 007 task).
