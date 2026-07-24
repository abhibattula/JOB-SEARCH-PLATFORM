# Feature 011 "The Coverage Release" (v1.1.0): fill the fields today's engine can't

## Context

v1.0.1 made the companion connect reliably. But its fill *coverage* stops at
a hard wall: the filler only writes native inputs and native `<select>`
elements. Every **custom dropdown** (a `<div role="combobox">` / React-Select
widget — used for work-authorization, EEO, "how did you hear", and most
Workday fields) is reported "fill this one yourself", and there are **no
adapters for Workday, iCIMS, or Taleo** — exactly the sites the user's
hardware target list runs on (NVIDIA/AMD/Qualcomm/Intel are Workday). The
result: on a real Workday application the companion fills almost nothing.

The blocker is the companion's self-imposed **zero-`.click()` invariant**
(asserted by `tests/test_extension_assets.py::test_filler_never_clicks` and
mirrored in `watcher.py`). A custom dropdown can only be set by clicking it
open and clicking an option — so raising coverage *requires* relaxing that
invariant, carefully.

### User-locked decisions (AskUserQuestion, 2026-07-24)

- **Allow field-value-only clicks.** The companion may click a field's own
  widget (a dropdown control + its option, a typeahead suggestion) to SET A
  VALUE — the same intent as typing. A hard **denylist** blocks any click on
  submit / apply / next / continue / save / finish / login / pay controls
  (matched by normalized text + `type` + `role`), enforced by test in both
  backends. The human still performs every real submit/login.
- **Targets:** Workday, custom dropdowns everywhere (incl. on Greenhouse/
  Lever/Ashby), iCIMS/Taleo, and more depth on the three already-working ATS.
- Still $0, offline-first, never auto-submits, engine never imports web.

## The safety model change (the crux)

Today the constitution says "the human always performs the final submit/
login action" and "MUST NOT auto-submit on the user's behalf." Clicking a
field's own dropdown to choose a value is neither a submit/login nor a
bot-protection bypass — so this is within the constitution's actual wording;
what changes is the *implementation's* stricter zero-click rule.

New enforced guarantee (replaces "never clicks anything"):

> The companion may click ONLY an element it is actively setting a value on
> (a form field or that field's own popup option). Every click is gated
> through `isSafeToClick(el)`, which returns false for anything that is or
> contains a submit/apply/next/continue/save/finish/login/register/pay
> control — matched on normalized text, `type=submit`, `role=button` with
> those labels, and known ATS submit selectors. A denylisted control is
> never clicked, in any backend, ever.

A one-line **constitution clarification** (Principle III) records this bounded
relaxation so the gate is the documented contract, not a silent loosening.

## Architecture (5 workstreams)

### WS-A — the safe-interaction gate (shared contract, both backends)

- `engine/autofill/click_guard.py` (NEW): the single source of truth for the
  denylist — `SUBMIT_DENY_PATTERNS` (regex over normalized text: apply,
  submit, next, continue, save, finish, review, login, sign in, register,
  create account, pay…) + `is_denylisted(text, type, role)`. Pure, unit-
  tested exhaustively.
- Extension mirror `extension/content/click_guard.js` (NEW): the same
  patterns in JS (can't import Python). A test asserts the two lists are
  term-for-term identical (`test_extension_assets.py`), so they can't drift.
- `filler.js`: new `safeClick(el)` that throws/aborts if
  `isDenylisted(...)` — the ONLY click path. Reframe
  `test_filler_never_clicks` → `test_filler_only_clicks_through_guard`
  (assert every `.click(` in filler.js is a `safeClick(` call; assert
  `click_guard.js` is imported).

### WS-B — custom dropdown + typeahead filling (the coverage win)

- **Scanner** (`extension/content/scanner.js` + watcher.py `SERIALIZE_JS`):
  serialize custom widgets, not just native. Detect `[role=combobox]`,
  `[role=listbox]`, `[aria-haspopup=listbox]`, React-Select containers
  (`.select__control`/`[class*="-control"]`), and Workday combo buttons.
  Add descriptor fields: `widget` (`native_select` | `custom_combobox` |
  `typeahead` | `""`), `automation_id` (Workday's `data-automation-id`),
  and the widget's current displayed value + readable options.
- **Protocol** (`engine/autofill/ext_protocol.py`): `FillItem.kind` gains
  `combobox` and `typeahead`; `Descriptor` gains `widget`, `automation_id`.
- **field_core** (`engine/autofill/field_core.py`): the existing
  `descriptor.get("options")` branch becomes widget-aware — native →
  `select` (unchanged), custom → `combobox`, typeahead-classified → `typeahead`;
  option-match still required (`fields.match_option`), else `no_match`.
- **Executors** (parity in both):
  - `filler.js`: `fillCombobox` = `safeClick(control)` → wait for the option
    list (MutationObserver, short timeout) → find option by normalized label
    → `safeClick(option)` → verify displayed value changed → dispatch
    input/change; on any failure report `needs_manual` and dismiss the popup
    (Escape). `fillTypeahead` = set value via native setter → wait for
    suggestions → `safeClick` the matching one.
  - `watcher.py`: the same via Playwright locators (`.click()` gated by
    `click_guard.is_denylisted` before every click) so the assistant-window
    fallback fills combos too (parity — FR: fallback loses nothing).
- Invariants preserved: non-empty sacred, focused-field skip, just-before-
  write recheck, idempotent ledger, secrets fill-and-forget.

### WS-C — harder-ATS adapters (`engine/autofill/adapters.py`, `fields.py`)

- **Workday**: host detector (`*.myworkdayjobs.com`, `*.wd{N}.myworkdayjobs.com`)
  + field map keyed on `data-automation-id` (stable across Workday tenants:
  `legalNameSection_firstName`, `email`, `phone-number`, `addressSection_*`,
  the source/how-heard combo, work-auth combos). Multi-step wizard: the
  watcher already keeps watching every frame each tick; the user clicks
  Workday's own Next/Continue (denylisted for us), each page re-scans and
  fills. Location/school **typeaheads** handled by WS-B's typeahead path.
- **iCIMS / Taleo**: host maps + legacy field-name patterns; iCIMS iframes
  already covered by `all_frames:true`.
- Generic classifier (`fields.py`) gains patterns so unmapped custom combos
  still classify by their label/aria (work-auth, EEO, how-heard, years-exp).

### WS-D — coverage visibility + fixtures + tests

- Fill report/summary already counts filled fields; add a per-job
  "N of M recognized fields filled" line so the user sees coverage rise, and
  keep `needs_manual` honest for genuinely un-fillable widgets.
- **New fixtures** (`tests/fixtures/ats_pages/`): `workday_style.html`
  (data-automation-id fields + a custom combo + a school typeahead + a
  disabled "Next" that must never be clicked), `icims_style.html`,
  `taleo_style.html`, and make `react_select_dropdown.html` actually
  fillable (its test flips from needs_manual → filled). Each mirrors real
  DOM values to `/echo`.
- **Tests**: `click_guard` unit matrix; field_core widget tests;
  adapters (Workday/iCIMS/Taleo) tests; ext_protocol kinds; reframed
  never-submit guard; and **real-browser integration** (`-m browser`,
  `--load-extension`) that actually FILLS a custom dropdown + a Workday-style
  page + a typeahead — plus a page with a submit button whose label matches
  an option, proving the denylist stops the companion clicking submit even
  when it looks fillable.

### WS-E — docs, version, ship

- README known-limitations + USER_GUIDE/USER_MANUAL: custom dropdowns and
  Workday now fill; the safety line updated ("clicks fields to set values,
  never submit/login"). Practice page gains a custom combo so the on-machine
  demo shows it.
- Version **1.1.0** (minor — new capability), What's New entry, constitution
  clarification commit, ship ritual (full ×2 + browser + slow gates → frozen
  smoke → live gate on a real Workday + Greenhouse posting → merge → mirror
  `main:001-ai-job-engine` → tag v1.1.0 → verify BOTH installers).

## Constitution guardrails (enforced by test)

Never click submit/apply/next/continue/save/finish/login/register/pay (the
denylist) · never auto-submit · never bypass bot protection (we run in the
user's own logged-in browser; we don't defeat Cloudflare/CAPTCHAs) · $0 ·
engine never imports web · visa/EEO answers still confirm-gated & never
AI-drafted · passwords fill-and-forget.

## Verification (must pass before shipping)

- `click_guard` denylist unit matrix green; JS/Python denylists proven
  identical.
- field_core emits combobox/typeahead correctly; option-match still gates.
- Real browser (`-m browser`): a custom dropdown, a Workday-style page, and a
  typeahead all FILL (echo shows the value landed); the submit-styled-option
  page proves submit is never clicked; existing 8 extension tests + the
  idle-recovery tests stay green.
- Playwright fallback fills the same combos (parity).
- Full `pytest -q` ×2 + `-m browser` + `-m slow` green; frozen build +
  `packaging/smoke_test.py` PASS; manual live gate on a real Workday posting
  in the user's own Chrome (fields + one custom combo fill; Next never
  clicked by the app).

## Process

New branch `011-coverage-release` → design doc committed → speckit chain
(specify → clarify → plan → checklist → tasks → analyze, fix all findings) →
hybrid speckit + superpowers TDD implementation → docs → frozen smoke → live
gate → ship v1.1.0. (Same pipeline as 010.)

## Non-goals

Auto-submit / auto-Next / auto-login (denylisted forever) · defeating
Cloudflare/CAPTCHA/bot-protection · Chrome Web Store publishing & code
signing (a separate "distribution" release) · discovery overlays on
LinkedIn/Indeed (a separate release) · scanned-image resume OCR.
