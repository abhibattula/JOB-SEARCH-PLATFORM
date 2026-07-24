# Implementation Plan: The Coverage Release (v1.1.0)

**Branch**: `011-coverage-release` | **Date**: 2026-07-24 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/011-coverage-release/spec.md`
**Design doc**: `docs/superpowers/specs/2026-07-24-feature-011-design.md` (approved)

## Summary

Raise Apply Assist's fill coverage on harder application pages by (1)
relaxing the companion's zero-`.click()` invariant to allow field-value-only
clicks behind a shared submit **denylist** guard, (2) filling **custom
dropdowns and typeaheads** (open → pick matching option → verify, or type →
pick suggestion; ~1.5s wait then give up cleanly), and (3) adding **Workday /
iCIMS / Taleo** ATS adapters (Workday keyed on stable `data-automation-id`).
Both fill backends reach parity (companion + Playwright fallback). The
enabling safety change is a shared `click_guard` (denylist matched on the
clicked element + its descendants, never ancestors), enforced by test in
both backends, plus a one-line constitution clarification.

## Technical Context

**Language/Version**: Python 3.12 (engine), JavaScript ES2022 (extension —
plain modules, no build step)
**Primary Dependencies**: existing only — Playwright, FastAPI, pydantic,
llama-cpp-python. NO new pip/npm dependencies.
**Storage**: none new (no schema change; adapters + guards are code)
**Testing**: pytest (markers browser/slow); real-extension integration via
Playwright `launch_persistent_context(--load-extension)` against local
fixture pages; JS validated through the integration layer + static asset
guards
**Target Platform**: Windows/macOS desktop app; Chrome/Chromium ≥116 for the
companion (assistant-window fallback covers the rest)
**Project Type**: desktop app (FastAPI + pywebview) + browser extension
**Performance Goals**: custom widget filled within ~2 scan passes of
appearing; per-widget popup wait ≤1.5s then abandon; fill continues across
Workday's multi-page wizard as the user advances it
**Constraints**: never click submit/apply/next/continue/save/finish/login/
register/pay (the denylist) · never auto-submit/advance · never bypass bot
protection · $0 · engine never imports web · visa/EEO confirm-gated & never
AI-drafted · passwords fill-and-forget
**Scale/Scope**: ~1 new engine module (click_guard) + 1 extension module +
edits to scanner/filler/watcher/field_core/adapters/fields/ext_protocol;
~5 new fixture pages; 3 new ATS adapters

## Constitution Check

*GATE: evaluated against constitution v1.1.1 — PASS with a one-line
clarification (not a principle change).*

- **I. Speed-to-Value**: filling more fields on the sites the user actually
  targets (Workday = the hardware employers) shortens apply time. Deferred
  list (auth/multi-user, hosted, CLI/MCP) untouched. PASS.
- **II. Zero-Subscription Cost**: no new dependency, service, store, or
  signing fee; offline-capable. PASS.
- **III. API-First / no bot bypass / human does submit-login**: the companion
  clicks ONLY a field's own widget to set a value — never submit/apply/next/
  login (the denylist, tested both backends); it never bypasses bot
  protection (runs as the user, in the user's session). This is within
  Principle III's wording ("the human always performs the final submit/login
  action"); we record it as a **written clarification** to Principle III so
  the field-value-click boundary is documented, not silent. PASS
  (clarification, not amendment).
- **IV. Reusable Core, Thin Web Layer**: `click_guard` denylist lives in
  `engine/autofill/` (pure); the extension mirrors it in JS with a
  parity test. Fill DECISIONS stay in `field_core` (shared). PASS.
- **V. Tested Core Logic**: click_guard matrix, field_core widget tests,
  adapter tests, and real-browser integration that actually fills custom
  widgets + proves submit is never clicked. PASS.

## Project Structure

### Documentation (this feature)

```text
specs/011-coverage-release/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output (live gate + walkthrough)
├── contracts/
│   └── fill-widgets.md  # widget-kind + fill-item + click-guard contract
└── tasks.md             # Phase 2 output (/speckit.tasks)
```

### Source Code (repository root)

```text
engine/autofill/
├── click_guard.py           # NEW — SUBMIT_DENY_PATTERNS + is_denylisted(el
│                            # text/type/role + descendant text); single
│                            # source of truth for "never click this"
├── field_core.py            # CHANGED — widget-aware decide(): native select
│                            # → "select"; custom → "combobox"; typeahead →
│                            # "typeahead"; option-match still gates (no_match)
├── adapters.py              # CHANGED — Workday (data-automation-id map +
│                            # host detect), iCIMS, Taleo host maps
├── fields.py                # CHANGED — classifier patterns for combo/
│                            # typeahead labels (work-auth, EEO, how-heard,
│                            # years-exp, location, school)
├── watcher.py               # CHANGED — SERIALIZE_JS serializes custom
│                            # widgets (role/aria/automation_id/displayed
│                            # value/options); Playwright combobox+typeahead
│                            # fill via locators, every click guarded
├── ext_protocol.py          # CHANGED — FillItem.kind += combobox|typeahead;
│                            # Descriptor += widget, automation_id
└── ext_backend.py           # CHANGED — emit combobox/typeahead fill items;
                             # unchanged report/ledger shapes

extension/
├── content/click_guard.js   # NEW — the denylist mirrored in JS (parity-
│                            # tested against click_guard.py term-for-term)
├── content/filler.js        # CHANGED — safeClick(el) (only click path,
│                            # throws on denylist); fillCombobox (open→wait
│                            # ≤1.5s→pick→verify→Escape on fail); fillTypeahead
├── content/scanner.js       # CHANGED — serialize custom widgets to match
│                            # SERIALIZE_JS parity
└── manifest.json            # CHANGED — content_scripts loads click_guard.js
                             # before filler.js

tests/
├── test_click_guard.py                  # NEW — denylist matrix (allow/deny)
├── test_extension_assets.py             # CHANGED — reframe never-click →
│                                         # only-clicks-through-guard; assert
│                                         # JS/Py denylists identical
├── test_field_core.py                   # CHANGED — combobox/typeahead kinds
├── test_adapters.py                     # CHANGED — Workday/iCIMS/Taleo
├── test_ext_protocol.py                 # CHANGED — new kinds/fields
├── test_watcher.py                      # CHANGED — Playwright combo parity
├── integration/test_extension_fixture_pages.py  # CHANGED — fill combo +
│                                         # Workday-style + typeahead; submit-
│                                         # styled-as-option never clicked
└── fixtures/ats_pages/                  # + workday_style.html, icims_style
                                          # .html, taleo_style.html,
                                          # typeahead.html; react_select_
                                          # dropdown.html made fillable

web/templates/practice_apply.html        # CHANGED — add a custom combo so the
                                          # on-machine demo shows it
.specify/memory/constitution.md          # CHANGED — 1-line Principle III note
packaging/jobengine.spec                 # CHANGED (assert) — click_guard.js
                                          # present; version 1.1.0 files
docs/{README,USER_MANUAL,USER_GUIDE}     # CHANGED — coverage + safety line
```

**Structure Decision**: single repo, existing layout. The denylist is the
one genuinely-shared safety contract; it lives once in Python
(`click_guard.py`) and is mirrored in `click_guard.js`, with a test that
fails if the two drift. Fill decisions stay in `field_core` (one place, both
backends). No new dependency or build tool — keeps $0 and PyInstaller simple.

## Key design decisions (detail: research.md)

1. **click_guard**: `is_denylisted(text, type, role)` over a regex set of
   normalized submit-class terms. The executor computes the verdict from the
   clicked element's own text/type/role **plus** the concatenated text/roles
   of elements it contains, and NEVER its ancestors (clarify Q1) — so an
   option inside a form with a Submit button is allowed, but a `<div>`
   wrapping a submit button is refused. Same patterns in JS; a test asserts
   the two term lists match.
2. **Widget serialization**: scanner/SERIALIZE_JS detect `[role=combobox]`,
   `[role=listbox]`, `[aria-haspopup=listbox]`, React-Select
   (`[class*="-control"]` under a `.select`/`[class*="select"]` container),
   and Workday combo buttons; emit `widget` + `automation_id` + displayed
   value + readable options. Native `<select>` keeps `widget="native_select"`
   (unchanged path).
3. **field_core widget-aware**: the existing options branch splits by widget
   → `select` | `combobox` | `typeahead`; `fields.match_option` still gates
   (no match → `no_match`; never a wrong option). Sensitive tags still route
   through the confirm-gate, never AI-drafted, even as a combobox.
4. **Executors (parity)**: `filler.js` fillCombobox = safeClick(control) →
   MutationObserver wait ≤1.5s for options → match by normalized label →
   safeClick(option) → recheck displayed value → input/change; on
   miss/timeout → Escape to close, report `needs_manual`. fillTypeahead =
   native-set value → wait ≤1.5s → safeClick matching suggestion. `watcher.py`
   mirrors via Playwright locators, each `.click()` preceded by
   `click_guard.is_denylisted` refusal.
5. **Workday**: host detect `*.myworkdayjobs.com` / `*.wd{N}.myworkdayjobs
   .com`; adapter map keyed on `data-automation-id`
   (`legalNameSection_firstName`, `email`, `phone-number`,
   `addressSection_*`, source/how-heard, work-auth). Multi-page: watcher
   already re-scans each frame each tick; the user clicks Workday's own Next
   (denylisted for us). iCIMS/Taleo: host maps + legacy field-name patterns;
   iCIMS iframes already covered by all_frames.
6. **Constitution**: append one sentence to Principle III clarifying
   field-value clicks are permitted while submit/login controls are
   never-clicked (governance note → v1.1.2 — clarification, not a principle
   change).

## Complexity Tracking

No violations. The one added surface (a shared denylist duplicated Py↔JS) is
mitigated by the parity test; everything else edits existing modules.
