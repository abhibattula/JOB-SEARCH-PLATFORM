# Tasks: The Moat Release

**Input**: Design documents from `/specs/007-moat-release/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/http-api.md

**Tests**: REQUIRED — constitution Principle V mandates pytest-first coverage for
engine/deterministic logic; the project's hybrid workflow applies superpowers
TDD (RED→GREEN) to every task pair below.

**Organization**: Phase 2 carries the design-system foundation (plan WS-4a)
because every story's UI lands on it; user stories then follow spec priority
with US2 before US1 (US1's tailored-PDF attachment consumes US2's output).

## Format: `[ID] [P?] [Story?] Description with file path`

---

## Phase 1: Setup

- [X] T001 Add pinned `fpdf2` to requirements.txt, install into .venv, verify `python -c "import fpdf"`
- [X] T002 [P] Add DejaVu Sans TTF family under assets/fonts/ (regular + bold) with license file
- [X] T003 [P] packaging/jobengine.spec: add assets/fonts datas entry with build-time existence assertion (tls_client-pattern)

---

## Phase 2: Foundational (blocking all stories)

- [X] T004 TDD: tests/test_db.py — roundtrip tests for new columns: user_profile (resume_file_path, resume_sections JSON, sections_edited_at), companies (h1b_denials, wage_level_median, wage_offered_median, cap_exempt, sponsor_grade), h1b_employers (denials, wage medians); watch fail
- [X] T005 engine/db.py — extend _MIGRATIONS, _PROFILE_COLUMNS, _PROFILE_JSON_FIELDS per data-model.md; tests green
- [X] T006 TDD: tests/test_settings.py + tests/test_api.py — THEME setting save/read via existing settings path; base template stamps `data-theme` from setting; watch fail → implement in web/routes_api.py + web/main.py + web/templates/base.html (incl. pre-paint inline theme script)
- [X] T007 web/static/styles.css — rebuild as full token system (semantic palette, spacing scale, type scale) with light "datasheet" default + `[data-theme="dark"]` scope theme + `prefers-color-scheme` fallback block; style the orphaned `.feed-table` class; WCAG 2.1 AA contrast in both themes (FR-021/FR-028)
- [X] T008 web/static/app.js (NEW) — toast component, `pollingAllowed()` gate, theme toggle, htmx loading/disabled hooks; wire into base.html
- [X] T009 web/templates/base.html — grouped nav (Search / Pipeline / Apply / Setup) with `aria-current` active state (FR-022)
- [X] T010 Poll-clobber fix (FR-024): conditional `hx-trigger="every 5s [pollingAllowed()]"` on feed/autofill polled regions + `hx-preserve` on stage/notes editors in web/templates/partials/feed_table.html; render test asserts gating/preserve attributes present

**Checkpoint**: suite green; app runs in both themes; polling no longer clobbers open editors.

---

## Phase 3: User Story 2 — Resume builder + tailored PDFs (P1)

**Goal**: uploaded resume → editable structured sections → per-job ATS-safe tailored resume + cover-letter PDFs.
**Independent test**: quickstart §1 (upload → review/edit → re-upload prompt → tailored PDF download).

- [X] T011 [US2] TDD: tests/test_resume_extract.py (NEW) — ResumeSections schema validation (partial extraction valid, empty-entry dropping), extraction via mocked matcher._chat, no-tier → None, malformed LLM output → bounded retry → None; watch fail
- [X] T012 [US2] engine/resume_extract.py (NEW) — pydantic ResumeSections + extract() via matcher._chat dispatch; tests green
- [X] T013 [US2] TDD: tests/test_api.py — resume upload stores original bytes (resume_file_path set, file exists under data dir), extraction_conflict flag when sections_edited_at set, PUT /api/profile/resume-sections validation (422 malformed), POST /api/profile/reextract (409 no resume, no-ai-tier reply, clears sections_edited_at); watch fail
- [X] T014 [US2] web/routes_api.py — implement stored-file save, extraction call + conflict flow, PUT resume-sections, POST reextract, extended GET /api/profile payload per contracts/http-api.md
- [X] T015 [US2] web/templates/partials/resume_builder.html (NEW) + include in profile.html — sections editor (experience/education/projects/skills), keep-vs-re-extract prompt, manual-entry parity; render test with populated + empty sections
- [X] T016 [US2] TDD: tests/test_resume_pdf.py (NEW) — renders parseable PDF (extract text back via fitz), tailored variant contains tailor bullets, untailored fallback without tailoring, unicode (en-dash/accents) renders, fingerprint cache hit/miss/invalidation; watch fail
- [X] T017 [US2] engine/resume_pdf.py (NEW) — fpdf2 + DejaVu fonts via paths.resource_path, single-column ATS layout, cover-letter renderer, fingerprint sidecar under data_dir()/tailored/
- [X] T018 [US2] TDD: tests/test_api.py — GET /api/jobs/{id}/resume-pdf (200 application/pdf, 409 no sections) and /cover-letter-pdf (409 no tailoring); watch fail → implement routes in web/routes_api.py
- [X] T019 [US2] web/templates/job_detail.html — "Download tailored resume (PDF)" + cover-letter PDF buttons beside tailor output
- [X] T020 [US2] GET /api/diagnostics/pdf-selftest route in web/routes_api.py (beside the existing local-llm/chromium selftests) + packaging/smoke_test.py assertion (real render, non-trivial byte count); test in tests/test_diagnostics.py

**Checkpoint**: US2 independently deliverable (quickstart §1 passes live).

---

## Phase 4: User Story 1 — Apply Assist depth (P1)

**Goal**: real applications get resume attachment, multi-page fill, a trustworthy fill report, structured-input answers, and queue recovery.
**Independent test**: quickstart §2 on a real Greenhouse/Lever posting.

- [X] T021 [US1] TDD: tests/test_fields.py — option-matching classification support: select/radio/checkbox descriptors carry options list; matcher picks best option text for confirmed answers, returns None below confidence; watch fail
- [X] T022 [US1] engine/autofill/fields.py — options in serialized descriptors + match_option() helper (confidence threshold is a named module constant, exercised from both sides by T021's match/no-match cases); tests green
- [X] T023 [US1] TDD: tests/test_browser_controller.py — (a) resume field attaches stored file via set_input_files (mocked page), tailored PDF preferred when fingerprint-fresh + setting on; when set_input_files raises (custom widget), outcome recorded as needs-manual and the queue continues; (b) idempotency: non-empty fields skipped, file inputs skipped when populated (FR-007); (c) fill report records label/tag/value_preview/outcome, password recorded pre-masked "•••" (FR-005); (d) page-URL-change triggers re-scan pass, confirmation gates still pause (FR-003); (e) TargetClosed → interrupted state preserving queue position; resume_queue() relaunches at current job (FR-008); (f) queue end produces batch summary (FR-009); (g) never-click assertion: across a full multi-page fill pass, the mocked page records zero click()/press() invocations on any button, submit, link, or navigation element (FR-004/SC-006); watch all fail
- [X] T024 [US1] engine/autofill/browser_controller.py — file attachment (generic + tailored-preferred), idempotent fill pass, fill-report recording with record-time masking
- [X] T025 [US1] engine/autofill/browser_controller.py — page-change detection on the controller thread + rescan pass; manual rescan command
- [X] T026 [US1] engine/autofill/browser_controller.py — interruption detection, resume_queue(), per-job outcomes + batch summary
- [X] T027 [US1] TDD: tests/test_routes_autofill.py — extended status payload (queue list with title/company/state, progress, current title+company, fill_report, interrupted, summary), POST /api/autofill/rescan (409 no session), POST /api/autofill/resume-queue (409 nothing to resume); watch fail
- [X] T028 [US1] web/routes_autofill.py — implement rescan + resume-queue routes and extended status per contracts/http-api.md
- [X] T029 [US1] web/templates/autofill.html + partials/autofill_status.html — mission-control rebuild: queue list (done ✓ / current ▸ / pending / failed), "N of M" progress, current job title+company, per-field fill report, interrupted banner + Resume button, batch summary view, select-all/none on job list (FR-026)
- [X] T030 [US1] AUTOFILL_USE_TAILORED_PDF setting (default on) + Settings page toggle; test in tests/test_settings.py

**Checkpoint**: US1 independently deliverable (quickstart §2 passes live; SC-006 never-clicks assertions in suite).

---

## Phase 5: User Story 3 — Sponsorship intelligence (P2)

**Goal**: local A–F sponsor grades, cap-exempt badges, wage/lottery insight, strong-sponsors filter.
**Independent test**: quickstart §3 with real USCIS/DOL files.

- [ ] T031 [US3] TDD: tests/test_sponsorship.py — wage-level/offered-wage column capture from fixture frames (with and without those columns → FR-010 tolerance), denial-column summing, per-employer medians; watch fail
- [ ] T032 [US3] engine/sponsorship.py — extend load_dol_dir/load_uscis_dir/store_employers for denials + wage data
- [ ] T033 [US3] TDD: tests/test_sponsor_grade.py (NEW) — grade formula bands (A≥85…F), ≥10-petition floor → None below (FR-011), cap-exempt heuristic true/false cases incl. word-boundary non-matches ("Universal Instruments" ≠ university), lottery hint from median wage level; watch fail
- [ ] T034 [US3] engine/sponsorship.py — grade(), cap_exempt(), lottery hint; recompute inside apply_to_companies(); tests green
- [ ] T035 [US3] TDD: tests/test_api.py — feed rows carry sponsor_grade/cap_exempt, strong_sponsors=1 filter (grade ≥ B or cap-exempt, composes with existing params), detail sponsor_evidence object per contracts; watch fail
- [ ] T036 [US3] engine/db.py query_jobs strong_sponsors param + payload fields; web/routes_api.py param + detail evidence
- [ ] T037 [US3] web/templates/partials/feed_table.html + job_detail.html + feed.html — grade badge, cap-exempt badge, evidence panel (approvals/denials/rate/wage/lottery hint/grade reasons, estimate labeling per FR-013), "Strong sponsors only" toggle

**Checkpoint**: US3 independently deliverable (quickstart §3 passes against real data).

---

## Phase 6: User Story 4 — Redesign completion (P2)

**Goal**: kanban pipeline, onboarding checklist, full restyle, accessibility pass.
**Independent test**: quickstart §4 in both themes.

- [ ] T038 [US4] TDD: tests/test_api.py — Applied board view renders (stage columns + counts partial), view toggle param; watch fail
- [ ] T039 [US4] web/templates/partials/pipeline_board.html (NEW) + feed.html toggle + app.js native DnD + per-card ◀/▶ buttons hitting existing POST /api/jobs/{id}/stage with toast (FR-025)
- [ ] T040 [US4] Onboarding checklist: web/templates/partials/onboarding.html (NEW), server-derived completion state in web/main.py (profile/resume/sponsorship/key/chromium), ONBOARDING_DISMISSED setting; render tests for fresh vs complete states (FR-027)
- [ ] T041 [US4] Restyle remaining pages on the token system: profile.html (incl. resume drop zone), settings.html, analytics.html, job_detail.html; all page render tests stay green
- [ ] T042 [US4] Accessibility pass: aria-labels on ☆ ✓ ✕ and all icon-only controls, aria-live="polite" on polled regions, table captions/scope, focus states audit; render tests assert accessible names present (FR-028)
- [ ] T043 [US4] Both-themes verification: parametrized render smoke across all pages with THEME=light/dark; fix any hardcoded-color leftovers

**Checkpoint**: US4 deliverable — quickstart §4 passes in both themes.

---

## Phase 7: Polish & Ship

- [ ] T044 Docs: docs/USER_MANUAL.md + docs/USER_GUIDE.md — resume builder, PDFs, Apply Assist depth, sponsor grades, themes, kanban, onboarding
- [ ] T045 Version bump 0.7.0: engine/__init__.py, packaging/windows.iss, packaging/jobengine.spec
- [ ] T046 Full suite ×2 + live quickstart walkthrough (all four sections) against the dev app with isolated data dir
- [ ] T047 Frozen verification: pyinstaller build + packaging/smoke_test.py (incl. pdf-selftest) on the real exe
- [ ] T048 Ship: merge/push per workflow, tag v0.7.0, both CI installers green, artifacts confirmed on the Release page

---

## Dependencies

- Phase 1 → Phase 2 → all story phases.
- US2 before US1 (T023's tailored-preferred attachment consumes T017's renderer + fingerprint).
- US3 independent of US1/US2 (may run in parallel with Phase 4 if desired).
- US4 Phase 6 depends only on Phase 2 (but lands last so restyles cover the new US1–US3 UI).
- Phase 7 last.

## Parallel opportunities

- T002 ∥ T003 (fonts vs spec file).
- Within Phase 2: T007 ∥ T008 after T006 (CSS vs JS, different files).
- Phase 5 (US3, engine-heavy) ∥ Phase 4 (US1, autofill-heavy) — disjoint files throughout.
- T044 ∥ T045 in Phase 7.

## MVP scope

Phases 1–3 (foundation + US2) already deliver a shippable increment:
redesigned foundation + resume builder + tailored PDFs. US1 completes the
P1 pair; US3/US4 finish the release.

## Format validation

All 48 tasks: checkbox ✓, sequential T-IDs ✓, [P] only on truly parallel
tasks ✓, [Story] labels on story-phase tasks only ✓, explicit file paths ✓.
