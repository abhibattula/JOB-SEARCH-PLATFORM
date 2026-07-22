# Feature 007 Design — The Moat Release

**Date**: 2026-07-21
**Status**: Approved by user (brainstorming session, all decisions confirmed individually)
**Ships as**: one release, v0.7.0, gated behind Phase 0 (v0.6.1 mac CI fix)

## Why

v0.6.0 (Profile overhaul) is code-complete but half-shipped — the mac-dmg CI
job failed at pytest, so only the Windows installer exists for the tag. The
user asked what the next phase should contain to make this **the most unique
job-search + application platform**, explicitly requesting a competitor
comparison, Apply Assist improvements, and a frontend/UI assessment.

Competitive research (2026): Simplify Copilot, JobRight, JobCopilot,
JobWizard, Teal, LazyApply, Sonara, FastApply are all cloud SaaS at
$20–40/mo or capped free tiers. Table stakes: ATS autofill, screening-answer
reuse, resume tailoring/generation, tracking. **None are local-first, none
bundle an offline LLM, and none integrate real sponsorship intelligence.**
H1BGrader / H1BVisaJobs have sponsorship data but aren't application tools.
This app's moat — 100% local, $0, private, sponsorship-aware on real
USCIS/DOL data, never-auto-submit — gets decisively deepened on every pillar.

## Locked decisions (each individually user-confirmed)

1. **Scope**: all four workstreams below ship together as **one big v0.7.0**.
2. **Structured resume data**: **AI-extract, user edits** — LLM parses the
   uploaded resume into structured sections; the user reviews/edits in a new
   Profile "Resume builder" section; manual entry is the no-LLM fallback.
3. **Visual direction**: **"Instrument, evolved"** — the existing
   datasheet/lab-instrument DNA executed as a real design system.
4. **Default theme**: **light-first** ("datasheet on paper"); the dark
   "scope screen" theme is the alternate, toggle persisted in Settings,
   `prefers-color-scheme` respected.

## Phase 0 — finish shipping v0.6.0 (gates everything)

mac-dmg failed `python -m pytest -q` in ~5s (a real test failure, not a
hang; Windows + Ubuntu were green — likely macOS-specific, plausibly in the
006 credential/keyring or profile tests). Get the log (`gh auth login`, then
`gh run view 29876833354 --log-failed`), root-cause via systematic
debugging, add a regression test, fix, tag **v0.6.1**, confirm both
installers on the Release page.

## WS-1 — Apply Assist depth

All in `engine/autofill/` + `web/routes_autofill.py` + the status partial.

- **Resume file upload**: store the original uploaded PDF at
  `paths.data_dir()/resume/<filename>` (today only extracted text survives;
  the bytes are discarded). `browser_controller` fills
  `resume_upload`-tagged file inputs via Playwright `set_input_files`.
  When the job has a tailored PDF (WS-3), that file is used instead of the
  generic one — user-visible toggle, default on.
- **Multi-page applications**: the human clicks the site's own
  Next/Continue; the controller detects in-tab navigation/DOM replacement
  and auto-rescans + fills each new page, plus a manual "Re-scan this page"
  button. The never-click-anything rule is preserved exactly.
- **Per-field fill report**: every fill recorded as
  `(label, tag, value-preview)`; the status panel lists what was filled so
  the user can trust-but-verify.
- **Structured inputs**: option-text matching for selects/radios/checkboxes
  (work-authorization yes/no, country/state, how-heard lists) — currently
  the weak path on real Greenhouse/Lever/Ashby forms.
- **Queue robustness**: detect a manually-closed browser window and allow
  resuming from the current position; per-job outcome record
  (filled/manual/skipped) feeding a batch summary when the queue ends.

## WS-2 — Sponsorship intelligence

Extends `engine/sponsorship.py` (don't replace):

- `load_dol_dir()` currently keeps only employer/title/SOC — additionally
  capture prevailing-wage level (I–IV) and offered-wage columns; store
  per-employer medians.
- `load_uscis_dir()` currently sums only "approval" columns — also read
  denial columns.
- **Sponsor grade (A–F)** per company from approval volume, denial ratio,
  engineering-LCA presence, and wage level. Feed badge + detail-page
  evidence panel.
- **Cap-exempt detection**: name-pattern heuristic (university / college /
  hospital / research institute / foundation) — these employers skip the
  H-1B lottery and sponsor year-round; distinct badge, directly actionable
  for an OPT candidate.
- **Wage-weighted lottery insight**: the 2026 wage-weighted selection rule
  favors higher wage levels — show a per-company lottery-odds hint from its
  median LCA wage level.
- Feed filter: "Strong sponsors only" (grade ≥ B or cap-exempt).

## WS-3 — Resume builder + tailored resume PDF export

- **Structured extraction**: on resume upload, the LLM (cloud or local
  tier — reuses `matcher._chat` dispatch) parses `resume_text` into
  structured sections: experience (title/company/dates/bullets), education,
  projects, skills. Stored as JSON on `user_profile`. A "Resume builder"
  section in Profile renders it for review/editing — the user always
  controls what the PDF says; nothing unreviewed is published. No LLM
  available → the same forms, filled manually.
- **`engine/resume_pdf.py`** renders an ATS-safe single-column PDF via
  **fpdf2** (pure Python, no native deps — PyInstaller-safe; weasyprint's
  GTK chain explicitly avoided). Header from 006 identity fields +
  structured sections; per-job variant swaps in `tailor.py`'s
  summary/bullets.
- Job detail page: "Download tailored resume (PDF)" + cover-letter PDF
  download next to the existing tailor output.

## WS-4 — Full visual redesign ("Instrument, evolved")

HTMX/Jinja architecture kept — no SPA rewrite. Use the `frontend-design`
skill during implementation. Grounded in the UI audit of
`web/templates/*` + `web/static/styles.css`:

- **Design system first**: complete token set (semantic palette, spacing
  scale, type scale) in CSS variables; light "datasheet on paper" default,
  dark "scope screen" alternate (phosphor-trace accents, status lamps,
  mono numerals). Kill the ~15 hardcoded hexes; style the completely
  unstyled `.feed-table` class (4 tables currently render browser-default).
- **Signature element**: the refresh channel-strip reborn as a live
  instrument trace across the top of the feed.
- **Navigation**: 11 flat links → grouped nav (Search / Pipeline / Apply /
  Setup) with active-page state (`aria-current`).
- **Feedback layer**: shared JS module — toasts for every action (currently
  zero visible confirmation for up to 5s), loading/disabled states on all
  `hx-post` buttons.
- **Poll-clobber fix** (correctness, not cosmetics): the 5s feed poll swaps
  DOM out from under in-progress notes/stage edits — pause polling while an
  editor is open, or use morphing swaps.
- **Pipeline kanban**: stage-column board (applied/OA/interview/offer/
  rejected) with counts; table view stays as a toggle; HTMX-native moves,
  no heavy DnD library.
- **Apply Assist mission-control panel**: queue list with per-job state
  (done ✓ / current ▸ / pending / failed), "3 of 8" progress, current job
  shown as title+company (not `#42`), WS-1's fill report, batch summary.
- **First-run onboarding**: persistent checklist card (resume → profile →
  sponsorship data → optional key → Apply Assist) with completion tracking.
- **Accessibility pass**: aria-labels on icon-only ☆ ✓ ✕ buttons, aria-live
  on polled regions, contrast-checked badges, resume drag-drop zone.

## Execution order

1. Phase 0 → v0.6.1 fully shipped.
2. `/speckit.specify` 007 → clarify → plan → tasks (hybrid workflow).
3. WS-4a: design system, tokens, both themes, unstyled-table + poll-clobber
   fixes (the foundation everything else's UI lands on).
4. WS-3: resume builder + PDFs (self-contained, immediately visible).
5. WS-1: Apply Assist depth (largest; its new status UI lands on WS-4a).
6. WS-2: sponsorship intelligence (data + scoring, then badges/filters).
7. WS-4b: kanban, nav, onboarding, a11y polish.
8. Docs, version → 0.7.0, full suite ×2, live walkthrough, frozen smoke
   test (add a PDF-generation self-test route), tag, both installers green.

## Testing

- TDD per workstream using existing patterns: fixture-dict classifier
  tests, fake-keyring-style fakes, template render tests, route contracts.
- Live: real Greenhouse/Lever application filled including resume file
  upload and a multi-page form; tailored PDF downloaded and attached;
  sponsor grades/cap-exempt badges on real USCIS+DOL data; both themes,
  kanban, and toasts exercised in the real app window.
- Frozen: rebuild installer; `packaging/smoke_test.py` gains a
  PDF-generation self-test (v0.4.0 lesson: real execution, not just state).

## Out of scope (unchanged deferrals)

Browser extension, auto-submit/auto-login (constitutionally banned),
LinkedIn automation, interview-prep coach (next-phase candidate), referral
finding, multi-user, code signing, embeddings/vector search.
