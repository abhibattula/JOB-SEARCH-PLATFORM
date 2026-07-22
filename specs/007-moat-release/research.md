# Research: The Moat Release (007)

All NEEDS-CLARIFICATION items from the technical context resolved below.
Product-level decisions were resolved in the brainstorming design doc
(`docs/superpowers/specs/2026-07-21-feature-007-design.md`) and the spec's
Clarifications session; this file records the *technical* decisions.

## 1. PDF generation library

**Decision**: `fpdf2` (pinned), pure Python.
**Rationale**: no native dependencies → zero PyInstaller bundling risk
(the v0.4.0 tls_client incident and 005's llama_cpp/playwright bundling
both came from native libs); active maintenance; simple flowing-text API
suited to a single-column ATS resume; LGPL (free, constitution II).
**Alternatives considered**: reportlab (heavier, BSD, fine but more API
surface than needed); weasyprint (rejected: GTK/Pango native dependency
chain — exactly the packaging risk class we avoid).

**Fonts/unicode**: fpdf2's built-in core fonts are Latin-1 only; resume
text routinely contains en-dashes, bullets, accented names. Decision:
bundle the DejaVu Sans TTF family (free Bitstream Vera license) as data
files (registered via `add_font(...)`), added to `packaging/jobengine.spec`
`datas` with a build-time existence assertion (established pattern).

## 2. Structured resume extraction

**Decision**: new `engine/resume_extract.py` with a pydantic schema
(`ResumeSections`: experience[], education[], projects[], skills[]; each
entry typed with title/organization/dates/bullets) extracted via the
existing `matcher._chat` tier dispatcher (cloud → local), one bounded
retry, schema-validated — exactly the `MatchAnalysis`/`tailor.py` idiom.
**Rationale**: reuses the proven LLM plumbing (throttle, provider
agnosticism, validation-with-retry); no LLM → returns None and the UI
falls back to empty manual forms (FR-017).
**Alternatives considered**: deterministic section-header parsing
(rejected as primary: resume formats vary too much; kept implicitly as the
manual-entry fallback), third-party resume-parser packages (rejected:
unmaintained/heavyweight/cloud-dependent).

## 3. Storing the original resume file + structured sections

**Decision**: save uploaded bytes to `paths.data_dir()/resume/<filename>`;
`user_profile` gains `resume_file_path` (TEXT) and `resume_sections`
(JSON TEXT, added to `_PROFILE_JSON_FIELDS`/`_PROFILE_COLUMNS`).
Re-upload with existing user-edited sections returns an
`extraction_conflict` flag; the UI asks keep-vs-re-extract
(clarified in spec); `sections_edited_at` timestamp distinguishes
"user touched" from "as extracted".
**Rationale**: single-profile model preserved; JSON column follows the
existing `skills`/`target_locations` idiom; file on disk (not a BLOB)
because Playwright `set_input_files` takes a path.

## 4. Tailored PDF lifecycle

**Decision**: render on demand to `paths.data_dir()/tailored/<job_id>.pdf`;
store the render's input fingerprint (hash of resume_sections +
tailor_json) alongside; serve/attach only when the fingerprint matches,
else re-render transparently. Existing `clear_all_tailoring()` on resume
change already invalidates the tailoring layer beneath.
**Rationale**: satisfies FR-020 (never stale) without a new invalidation
subsystem; on-demand render is fast (<1s) so caching is a convenience,
not a requirement.

## 5. Multi-page application detection (never clicking anything)

**Decision**: the browser-controller thread (sole Playwright owner)
listens for page URL changes and load-state transitions on the current
tab; on a settled new page (same tab, any URL — classification rules make
cross-site pages safe), it re-serializes fields and runs the normal
classify-and-fill pass. A `POST /api/autofill/rescan` route provides the
manual fallback for SPA re-renders that never navigate.
**Idempotency (FR-007)**: before filling, skip any field whose current
value is non-empty (user-typed or previously filled); never write into a
non-empty input; file inputs are skipped if already populated.
**Rationale**: event-driven detection stays inside the existing
single-thread ownership model; the non-empty-skip rule is simple,
testable, and makes repeated passes safe by construction.
**Alternatives considered**: MutationObserver-injected JS bridge
(rejected: complexity, still needs the same fill pass); polling DOM
signatures (kept as fallback via the manual rescan button).

## 6. Queue recovery after browser close

**Decision**: `browser_controller` catches Playwright
disconnect/TargetClosed errors, marks the session `interrupted`
(preserving the in-memory queue + position), and `start`/`resume`
relaunches the persistent context and re-opens the current job. In-memory
only — an app restart clears it (documented limitation, spec assumption).
**Rationale**: the queue state already lives in the controller's
module-level state; persistence to DB adds schema + staleness questions
for a case (app restart mid-queue) the spec explicitly scopes out.

## 7. Fill report & batch summary

**Decision**: per-job list of `{label, tag, value_preview, outcome}`
entries in controller state, exposed through the existing status
endpoint; credential passwords recorded only as the literal masked
marker (clarified in spec — the secret never enters controller state:
the mask is written at record time, not display time). Batch summary is
computed from per-job outcome records when the queue ends.
**Rationale**: masking at record time makes leaking impossible by
construction; no new tables (session-scoped data).

## 8. DOL wage + USCIS denial columns

**Decision**: extend `sponsorship.load_dol_dir()` column sniffing
(`_find_column`) for `PW_WAGE_LEVEL` ("wage", "level") and offered wage
("wage_rate_of_pay_from" → "wage", "from"); normalize levels to I–IV;
store per-employer median level + median offered wage. Extend
`load_uscis_dir()` to also sum columns containing "denial". New columns
on `h1b_employers` and `companies` via the established `_MIGRATIONS`
ALTER-TABLE idiom. Files lacking these columns behave exactly as today
(FR-010).
**Rationale**: same tolerant column-sniffing already proven against
year-to-year header drift in these files.

## 9. Sponsor grade formula

**Decision** (deterministic, unit-tested):
eligible only when approvals+denials ≥ 10 (clarified floor). Score =
approval_rate (55%) + volume band (25%: log-scaled approvals) +
engineering-LCA presence (10%) + wage-level band (10%: median ≥ III
full credit). Bands: A ≥ 85, B ≥ 70, C ≥ 55, D ≥ 40, else F.
Cap-exempt flag is independent of the grade (a cap-exempt employer may
be UNKNOWN-graded but still badged).
**Rationale**: approval rate is the strongest signal; volume guards
against tiny-sample flukes past the floor; weights are explainable on
the evidence panel. Exact weights are code constants with tests — easy
to tune later without schema changes.

## 10. Cap-exempt heuristic

**Decision**: word-boundary regex over the normalized employer name:
university|college|institute of technology|school of|hospital|medical
center|health system|research (institute|center|foundation|laboratory)|
national laboratory|academy of — plus a small curated allowlist file for
known cap-exempt names that dodge the patterns. Marked "likely
cap-exempt" (estimate language per spec).
**Rationale**: mirrors `filters.py`'s proven keyword-classifier style;
word-boundary regexes avoid the ITAR/"military" class of false match.

## 11. Theming without a build step

**Decision**: full token set as CSS custom properties on `:root`
(light default) with a `[data-theme="dark"]` override block; explicit
user choice stored in the `settings` table and stamped onto `<html>` by
the base template; when no explicit choice, a `prefers-color-scheme:
dark` media block applies the same dark tokens. A tiny inline head
script applies the stored theme before first paint (no flash).
**Rationale**: pure CSS + one setting; no build step (constitution
stack constraint); explicit-choice-wins ordering matches the spec.

## 12. Poll-clobber fix

**Decision**: gate the polling triggers with HTMX's conditional-polling
syntax (`hx-trigger="every 5s [pollingAllowed()]"`), where the shared JS
module's `pollingAllowed()` returns false while any editor inside the
polled region has focus or an open `<details>` notes editor exists;
additionally `hx-preserve` on the stage/notes editors as belt-and-
suspenders.
**Rationale**: solves the correctness bug with vendored-HTMX built-ins —
no morphing library needed (idiomorph rejected: another vendored dep for
a problem conditional polling already solves).

## 13. Kanban drag-and-drop

**Decision**: native HTML5 drag events (`draggable="true"`,
drop targets per column) wired in the shared JS module, calling the same
`POST /api/jobs/{id}/stage` endpoint as the ◀/▶ buttons; buttons remain
the keyboard/AT path (clarified in spec). No DnD library.
**Rationale**: desktop-app webview (Edge WebView2/WKWebView) fully
supports HTML5 DnD; identical endpoint keeps one code path for state.

## 14. Onboarding checklist state

**Decision**: computed server-side each render from real state (profile
row, resume_file_path, sponsorship record count, key present, Chromium
installed) — no stored "step done" flags; a single `onboarding_dismissed`
setting hides it permanently once all steps complete (or on explicit
dismiss).
**Rationale**: derived state can't drift from reality; matches FR-027.
