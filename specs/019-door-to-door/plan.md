# Implementation Plan: Door to Door

**Branch**: `019-door-to-door` | **Date**: 2026-07-31 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/019-door-to-door/spec.md`

## Summary

The companion escorts an application from the posting to the final
Review/Submit page: it clicks the posting's Apply control, signs in with the
user's saved login (OS credential vault), fills every wizard step, clicks
Continue/Next between completed steps, and parks in a prominent
"Review & submit — your turn" state. The human always presses the final
Submit. The same release fixes the verified reasons real pages still didn't
fill (version-skew invisibility, the v1.8.0 duplicate-tab bug, label /
shadow-DOM / Workday-widget / placeholder-select / visibility blind spots)
because escorting is only safe over pages that actually fill.

Technical approach: extension-first over the existing localhost WebSocket
bridge, all protocol changes additive (PROTOCOL_V stays 1). Two new modules
form the core pair — `engine/autofill/escort.py` (step-completeness
predicate, one-shot bookkeeping, caps, attribution, session states) and
`extension/content/advancer.js` (the only new click site, on the `opener.js`
allowlist template, mirroring `ADVANCE_ALLOWLIST` from
`engine/autofill/adapters.py`). Sign-in reuses the feature 005 credential
vault (`engine/credentials.py`, keyring → Windows Credential Manager /
macOS Keychain) and the existing fill-and-forget secret path. Governed by
constitution v1.2.0's progression-clicks clarification.

## Technical Context

**Language/Version**: Python 3.11+ (engine/, web/); vanilla ES2020 JavaScript
(MV3 extension — no framework, no build step)
**Primary Dependencies**: FastAPI + Jinja2 + HTMX (vendored), pydantic v2,
`keyring` (already a dependency, feature 005), pytest, Playwright
(test harness + legacy fill path)
**Storage**: SQLite `data/jobs.db` (never secrets); OS credential vault via
`keyring` (the only place secrets rest); `chrome.storage.session` for
non-secret arming/watch state
**Testing**: pytest unit + integration; real-Chromium suite (`-m browser`)
loading the real unpacked extension against a live in-process FastAPI app
over the real WebSocket bridge; frozen smoke via `packaging/smoke_test.py`
**Target Platform**: Windows 11 + macOS desktop app (PyInstaller installers
via GitHub Actions); Chrome/Chromium ≥ 116
**Project Type**: desktop web app + browser-extension companion
**Performance Goals**: posting → ready-for-review under 2 minutes on the
reference wizard fixture excluding human wait (SC-008); scan cadence
unchanged (500 ms debounce + 2 s safety poll)
**Constraints**: $0 recurring cost; offline-first; `engine/` never imports
`web/`; PROTOCOL_V stays 1 (additive fields only — `_Strict` uses
`extra="ignore"`); secrets fill-and-forget (never SQLite / chrome.storage /
logs / reports / feed / diagnostics); every automated click allowlist-first,
one-shot per step, capped, ledger-recorded, and paused on
needs-you/CAPTCHA/ambiguity (constitution v1.2.0)
**Scale/Scope**: single user; 5 user stories; ~130 tasks; ships as v1.9.0

## Constitution Check

*GATE: evaluated against constitution v1.2.0 before Phase 0; re-checked
after Phase 1 design.*

- **Principle I (Speed-to-Value)** — PASS. The feature is the user's explicit
  request and directly "helps the user complete and submit applications
  faster": one press from posting to review page.
- **Principle I/III click policy (v1.2.0 progression clicks)** — PASS. Every
  new click is one of the three permitted kinds (open-apply, wizard advance,
  state-gated sign-in) under the constitutional conditions: allowlist-first
  (FR-024), one-shot per rendered step (FR-026), hard cap 12 (FR-027),
  ledger-recorded (FR-031), mandatory pause on needs-you / CAPTCHA /
  ambiguity (FR-028/029). Final submit, Create account/Register/Sign up,
  pay/checkout, CAPTCHA, and LinkedIn clicks remain forbidden
  (FR-021/025/033) and are enforced by the final-class deny layer plus
  browser tests that prove the Submit control is never clicked (SC-006).
- **Principle II ($0)** — PASS. Reuses `keyring` + the OS vault; no new
  services, accounts, or paid components.
- **Principle III (polite ingestion)** — PASS. No new ingestion. The escort
  acts only inside pages the user chose to open; bot protection is never
  bypassed — CAPTCHA pauses to the human by design (FR-028).
- **Principle IV (reusable core, thin web)** — PASS. Escort policy and click
  taxonomy live in `engine/` (`escort.py`, `click_guard.py`, `adapters.py`);
  `web/` stays routes + templates; the extension mirrors engine allowlists
  with parity tests so policy cannot drift.
- **Principle V (tested core)** — PASS. The completeness predicate, click
  taxonomy, credential flows, and attribution windows are deterministic and
  unit-tested; every new interactive control gets a real-browser click test
  asserting its observable effect (the 018 lesson, spec SC-003/005/006/007);
  each scan/fill blind spot gets a dedicated fixture.

**Post-design re-check (after Phase 1)**: PASS — no violations introduced by
the design; Complexity Tracking stays empty.

## Project Structure

### Documentation (this feature)

```text
specs/019-door-to-door/
├── plan.md              # This file
├── research.md          # Phase 0 — decisions R1..R25
├── data-model.md        # Phase 1 — entities, states, protocol additions
├── quickstart.md        # Phase 1 — manual verification script
├── contracts/
│   ├── escort-protocol.md   # additive bridge messages + compatibility rules
│   └── escort-ui.md         # widget states, controls, final-class copy
├── checklists/
│   └── requirements.md  # spec quality gate (complete)
└── tasks.md             # Phase 2 (/speckit-tasks — not created by plan)
```

### Source Code (repository root)

```text
engine/
├── credentials.py                 # EXISTING (005) vault — gains generate_password()
└── autofill/
    ├── escort.py                  # NEW — predicate, one-shot keys, cap, attribution, states
    ├── ext_backend.py             # adopt-tab, busy fix, token TTL, credential_save,
    │                              #   advance_step dispatch, version-skew surfacing
    ├── ext_protocol.py            # additive: Descriptor.form_context, SessionState,
    │                              #   AdvanceStep/AdvanceResult, CredentialSave
    ├── field_core.py              # placeholder-value rule, prefilled_ok outcome
    ├── fields.py                  # login_email reachable, login_username, automation_id haystack
    ├── adapters.py                # ADVANCE_ALLOWLIST, expanded _WORKDAY_AUTOMATION, opener refresh
    ├── click_guard.py             # FINAL_TERMS layer beside DENY_TERMS; own-name judgment
    ├── browser_controller.py      # start_queue(adopt_tab_id=…); Playwright path unchanged
    ├── page_answers.py            # no_saved_login / version_mismatch needs-you reasons
    └── watcher.py                 # SERIALIZE_JS parity: labels, form_context

extension/
├── manifest.json                  # v1.9.0; advancer.js in content_scripts order
├── background/
│   ├── socket.js                  # reads hello_ok.app_version → mismatch state
│   ├── service-worker.js          # advance_step routing; mismatch to popup/panel
│   └── tabs.js                    # persist jobId (arming survives worker restart)
└── content/
    ├── click_guard.js             # FINAL_TERMS mirror; own-name judgment
    ├── scanner.js                 # label ladder, deepQueryAll (shadow), visibility,
    │                              #   form_context, login-wall + captcha probe
    ├── filler.js                  # UNTOUCHED click policy (one-click pin stays green);
    │                              #   promptOption harvest via shared deepQueryAll
    ├── opener.js                  # refreshed selectors; doc-token one-shot key
    ├── advancer.js                # NEW — the only new click site (allowlisted, one-shot)
    ├── panel.js                   # sign-in / your-turn / ready-for-review states,
    │                              #   save-login form, escort pause, new footer
    └── main.js                    # advance_step/advancer wiring, captcha report

web/
├── routes_bridge.py               # (already sends app_version) mismatch flag if needed
├── routes_api.py                  # credentials routes EXISTING (005)
├── main.py                        # WHATS_NEW["1.9.0"]
└── templates/
    ├── companion.html             # amber version-skew state
    └── settings.html              # auto-sign-in consent copy, escort toggle

tests/
├── test_escort_journeys.py                 # NEW — predicate/cap/one-shot/attribution tables
├── test_secret_hygiene.py         # NEW — grep logs/DB/storage/feed/doctor for the test secret
├── test_click_guard.py            # FINAL_TERMS + own-name tables (updated consciously)
├── test_extension_assets.py       # advancer asset pins + parity; footer string update
├── test_ext_backend.py / test_ext_protocol.py / test_fields.py /
│   test_field_core.py / test_adapters.py / test_credentials.py   # extended
├── integration/
│   ├── test_escort_journeys.py             # NEW flagship browser suite
│   ├── test_companion_widget.py   # apply-here test strengthened (tab count + real fill)
│   └── test_discovery_badge.py    # unchanged harness, reused
└── fixtures/ats_pages/
    ├── login_wall.html, registration.html, captcha_frame.html      # NEW
    ├── wizard_multipage/step1.html → step2.html → review.html      # NEW
    ├── wizard_spa.html, aria_labelledby.html, shadow_form.html     # NEW
    ├── workday_prompt_options.html, placeholder_select.html        # NEW
    └── fixed_modal_form.html, greenhouse_navigate_apply.html       # NEW
```

**Structure Decision**: existing two-package layout (engine core + thin web)
with the extension as a sibling — unchanged from 010-018. New logic goes in
one new engine module (`escort.py`) and one new extension module
(`advancer.js`) so the existing pinned invariants (`filler.js` single click
site, guard parity) stay intact; everything else is targeted edits to
existing files.

## Complexity Tracking

No constitution violations — table intentionally empty.
