# Implementation Plan: The Companion — the extension becomes the product

**Branch**: `018-companion` | **Date**: 2026-07-29 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/018-companion/spec.md`

## Summary

017 fixed *what* Apply Assist writes. The applicant could not use almost any of
it, because the surface it renders into is unreachable: both floating widgets
have rendered at the **bottom of the document** since v1.0.0 (`all:initial`
declared last in the host's inline style resets the `position:fixed` before it),
the badge's "Apply with Apply Assist" is a **dead button** (its handler reads a
`posting` key detection never sets), the answer feed carries **no field
identifier** so Insert and Show me never render, it lists **only AI-drafted
questions**, and it **destroys typed text every ~2 s** by rebuilding every row on
every scan. On a bare ATS application page, **nothing appears at all**.

This feature makes the extension the surface the applicant works in: one merged
floating companion, pinned to the viewport, that rests as a pill and expands to
show every answer with Copy / Insert / Show me, an input for anything the app
declined to answer, and full session control — so a single application needs
**zero** switches to the app.

The engine keeps all answering logic. The companion stays a thin client.

## Technical Context

**Language/Version**: Python 3.11+ (engine/web), ES2020 classic scripts
(extension — no modules in content scripts, no build step)
**Primary Dependencies**: FastAPI + Jinja2 + HTMX (vendored), pydantic v2,
Chrome MV3 (`storage`, `tabs`, `alarms`, `commands`; `host_permissions` for
127.0.0.1 only)
**Storage**: SQLite at `data/jobs.db` — **no schema change in this feature**
**Testing**: pytest; `@pytest.mark.browser` integration suite driving the real
unpacked extension in real Chromium against a live in-process FastAPI app over
the real WebSocket bridge
**Target Platform**: Windows + macOS desktop, Chromium-family browser
**Project Type**: Local desktop web app + MV3 browser companion
**Performance Goals**: no answer payload pushed when nothing changed (today: up
to 400 KB every 2 s); panel re-render must not drop a keystroke or lose focus;
the read-only form probe must be cheap enough to run on a 1.5 s tick on any page
**Constraints**: $0 recurring cost · offline-first · `engine/` never imports
`web/` · no JS framework, no Node build step · `PROTOCOL_V` stays 1 (additive
fields only) · no code signing · secrets never rendered, logged or transmitted ·
**Apply Assist never auto-submits**
**Scale/Scope**: single user; ~2100 lines of extension JS today; one new content
script; one new inbound message type; no new tables

## Constitution Check

*GATE: evaluated before Phase 0 and re-checked after Phase 1 design.*

| Principle | Assessment |
|-----------|-----------|
| **I. Speed-to-Value First** | PASS — directly serves "help the user complete and submit applications faster". Three shipped defects currently make the 017 investment unusable; this restores it and removes every mid-application tab switch. No deferred capability (auth, hosted deployment, CLI/MCP) is built. |
| **II. Zero-Subscription Cost** | PASS — no new dependency, service, or paid tier. All companion CSS is inline; no fonts, no CDN, no `web_accessible_resources`. |
| **III. API-First, Polite Ingestion** | PASS — no ingestion change. The new read-only form probe reads **only** the page the applicant is already looking at, sends **nothing** anywhere (its result decides local rendering only), and stamps nothing on the DOM. This is strictly *less* than the feature-012 clarification already permits, which allows reading job metadata and sending it to the local app. |
| **III (no-click/no-submit)** | PASS — unchanged. The companion clicks no page control. `Insert` places a value into the one field the applicant explicitly chose, which is field-filling under the feature-011 clarification. The click-guard denylist is untouched, and the applicant still performs every submit, login, and wizard step. |
| **IV. Reusable Core, Thin Web Layer** | PASS — the answer index and session control live in `engine/autofill/`; `web/` gains no logic (one template's post-submit behaviour changes). `engine/` imports nothing from `web/`. No answering logic moves into the extension. |
| **V. Tested Core Logic** | PASS, and strengthened — FR-039/FR-040 make real-browser interaction coverage a definition-of-done for every companion control, replacing the string-presence assertions that let a dead button ship. Deterministic engine additions (answer-index grouping, digest suppression, `session_control` validation) get pytest coverage before wiring. |

**No amendment required.** Nothing here relaxes a principle or a prior
clarification.

**Complexity Tracking**: not required — no violations.

## Project Structure

### Documentation (this feature)

```text
specs/018-companion/
├── plan.md                 # this file
├── spec.md
├── research.md             # R1–R14: root causes + platform decisions
├── data-model.md           # PageAnswer, CompanionState, FormProbe (no DB change)
├── quickstart.md
├── contracts/
│   ├── bridge-protocol-additions.md
│   └── companion-ui.md
├── checklists/
│   ├── requirements.md
│   └── companion.md
└── tasks.md
```

### Source code (repository root)

```text
extension/
├── manifest.json                 # merge the two content_scripts entries; add `commands`
├── background/
│   ├── service-worker.js         # route `error` to the tab; commands → active tab
│   └── tabs.js                   # unchanged
└── content/
    ├── scanner.js                # + probe(): READ-ONLY, stamps nothing
    ├── panel.js                  # NEW — the single companion widget
    ├── discovery.js              # detection/scoring kept; renders through panel
    ├── overlay.js                # REMOVED (facade lives in panel.js)
    ├── filler.js                 # unchanged
    └── main.js                   # drives the panel through the jeOverlay facade

engine/autofill/
├── ext_backend.py                # page-answer index, digest, session_control
├── ext_protocol.py               # SessionControl model (additive)
├── page_answers.py               # NEW — pure assembly/grouping/digest
└── browser_controller.py         # unchanged behaviour; reused stop/advance

web/templates/
└── job_detail.html               # start in place; stop navigating to /autofill

tests/
├── test_page_answers.py          # NEW — grouping, digest, je_idx presence
├── test_ext_backend.py           # answers feed coverage + suppression
├── test_ext_protocol.py          # session_control round-trip, PROTOCOL_V == 1
├── test_extension_assets.py      # negative invariants only
├── fixtures/
│   ├── discovery_pages/          # + hostile-CSS page, + bare application page
│   └── autofill_pages/           # + needs-you typing fixture
└── integration/
    ├── test_companion_widget.py  # NEW — real-browser click/position/typing tests
    └── test_discovery_badge.py   # retargeted onto the merged host
```

**Structure Decision**: existing layout. The one new engine module
(`page_answers.py`) is pure and follows the `field_core.py` / `vocab.py`
precedent: no I/O, no imports from `web/`, directly unit-testable. The one new
content script (`panel.js`) replaces `overlay.js` and absorbs the badge's
rendering while `discovery.js` keeps all detection and scoring.

## Phase plan

Each phase is independently shippable and independently testable. Tests are
written first, per the project's TDD workflow.

### US1 — I can see it, and it does something (P1)

The three defects that make everything else moot.

- Host style: `all:initial` first, then `position`/`inset`/`z-index`/`display`
  via `setProperty(..., "important")` (R1).
- `onApply` reads `current` directly (R2).
- `jeScanner.probe()` — read-only, non-stamping — plus the conservative
  form heuristic, so the companion appears on a bare application page (R7).
- Every primary-action click reports its outcome, including refusals (FR-010).

**Verification**: hostile-CSS 5000 px fixture asserts computed `position` and
on-screen rect; a real click on the primary action asserts the app received
`apply_here` / `fill_here` and started a session.

### US2 — One companion (P2)

- New `panel.js` owning `je-companion-host`; `window.jeOverlay` preserved as a
  facade; `discovery.js` renders through it; `overlay.js` removed.
- Pill ↔ card, auto-expand rules, viewport clamping, focus ring, reduced motion.
- Merge the two `content_scripts` entries so load order is explicit (R8).
- Light-DOM `data-je-*` mirror carries forward every attribute the 012/016/017
  suites assert, on the merged host.

### US3 — Answers worth reading (P3)

- New pure `engine/autofill/page_answers.py`: build, group, order, digest.
- `_handle_fields` assembles the index where `je_idx` is already in hand;
  drafter records merge in; secrets excluded.
- Digest suppression so an unchanged scan pushes nothing (FR-027).
- Keyed reconciliation in the panel; a row containing `root.activeElement` is
  never touched (R6 — note the shadow-root `activeElement` subtlety).
- Grouped collapsible rendering; Copy / Insert / Show me; needs-you input.

### US4 — Full control without the app (P4)

- `session_control` (`stop` | `next`) — additive inbound, delegating to the
  existing `browser_controller.stop_queue()` / `advance()`.
- `overlay_state.summary` gains optional `session`, `current_job_id`,
  `remaining`.
- `error` messages forwarded to the watched tab so refusals show in the card.
- `job_detail.html` starts a session in place instead of navigating (R12).
- `commands` in the manifest: toggle companion, fill current page (R11).

### US5 — Proof and ship

- Real-browser interaction suite (`tests/integration/test_companion_widget.py`).
- Retire the string-presence badge guards; keep only negative invariants.
- Docs: USER_MANUAL, README, `WHATS_NEW["1.8.0"]`.
- Full battery ×2 + `-m browser` + slow markers + offline-model gates; frozen
  smoke with `JOBS_AI_SUBPROCESS` on; version gate (`packaging/check_version.py`
  covers `windows.iss`); tag `v1.8.0`; verify **both** installers by magic bytes
  and SHA-256 against the release body.

## Risks and mitigations

| Risk | Mitigation |
|------|-----------|
| Replacing `overlay.js` breaks 016/017 behaviour `main.js` depends on | `window.jeOverlay` facade keeps the exact method surface; the existing panel tests run against it unchanged |
| The form probe puts a widget on ordinary pages | Conservative heuristic (≥3 fields, or file+field, or email+2), search-like inputs excluded; a real-browser test asserts no companion on a plain search page |
| Reconciliation is subtly wrong and still eats keystrokes | A test types into the input, lets ≥3 scan cycles pass, and asserts both text and focus survive — the specific failure being fixed |
| `commands` suggested keys clash with the browser or a site | Chrome drops a conflicting suggestion rather than failing to load; both commands are user-rebindable; the companion is fully usable by mouse |
| Digest suppression hides a genuine update | Digest covers every rendered field of every item, and `answers` is still re-sent on session start, `fill_again`, and any `answer_question` |
| A merged host regresses the 012 badge assertions | Every `data-je-*` attribute is carried forward and the existing badge tests are retargeted, not deleted |

## Non-goals

Firefox · store publication · code signing · a Node build step or JS framework ·
new ATS adapters beyond existing tag maps · auto-submitting anything · clicking
any page control the click-guard denylist covers · redesigning the app's own
pages beyond the `job_detail` entry point · changing the refusal contract or any
017 answer semantics · any database change.
