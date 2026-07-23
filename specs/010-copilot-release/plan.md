# Implementation Plan: The Copilot Release (v1.0.0)

**Branch**: `010-copilot-release` | **Date**: 2026-07-23 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/010-copilot-release/spec.md`
**Design doc**: `docs/superpowers/specs/2026-07-23-feature-010-design.md` (approved)

## Summary

Three pillars, one release: (1) a Manifest V3 Chrome extension becomes the
primary Apply Assist fill path — filling applications in the user's own
logged-in Chrome, connected to the local app over an authenticated
localhost WebSocket; the app remains the brain (classification, values,
answer bank, credentials, AI, queue, reports all stay in Python; the
extension only serializes DOM fields, fills instructed values, reports
outcomes); Playwright stays as automatic fallback. Includes ad-hoc "Fill
this page" mode. (2) AI drafting for open-ended questions grounded in the
user's resume/profile/answers (offline-first tier), draft → fill → flag
for review; drafts become saved answers on explicit confirm OR detected
submission. (3) Full UI overhaul: home dashboard, Apply Assist
connection-era screen, tracker board with notes/follow-ups and detected-
submission confirm, one visual identity.

## Technical Context

**Language/Version**: Python 3.12 (app), JavaScript ES2022 (extension — no
build step, no TypeScript, no bundler; plain modules)
**Primary Dependencies**: existing stack (FastAPI, uvicorn, Playwright,
llama-cpp-python, keyring, htmx) + FastAPI's native WebSocket support
(starlette, already present). NO new pip/npm dependencies.
**Storage**: existing SQLite via engine/db.py (new: ai_drafts fields on
answers, follow_ups on applications, bridge secret in settings) — additive
column migrations only (init_db is now race-safe, 009)
**Testing**: pytest (existing markers browser/slow); extension integration
via Playwright `launch_persistent_context(--load-extension)` against the
real app + existing fixture ATS pages; node-free JS (protocol validation
tested through the integration layer)
**Target Platform**: Windows 11 + macOS desktop app; Chrome/Chromium ≥116
for the companion (assistant-window fallback covers the rest)
**Project Type**: desktop app (FastAPI + pywebview) + browser extension
**Performance Goals**: connect ≤10s; fields fill ≤2 scan passes (~4s) of
appearing; AI draft ≤60s offline; UI state changes reflect ≤10s
**Constraints**: $0 (no store fee, unpacked distribution; no signing);
offline-fully-functional; never click/submit/login; engine never imports
web; passwords never persisted/logged extension-side, masked in reports
**Scale/Scope**: single user, single machine, one extension ↔ one app;
~15 new/changed Python modules, ~12 extension files, 4 UI surfaces

## Constitution Check

*GATE: evaluated against constitution v1.1.1 — PASS (no amendment needed).*

- **I. Speed-to-Value**: every pillar shortens apply time (fill where
  you're logged in; AI drafts for the slowest fields; next-actions
  surface work). Deferred list (auth/multi-user, hosted, CLI/MCP)
  untouched. App-driven browser automation is permitted per the approved
  005 amendment; the companion is the same capability relocated into the
  user's own browser, still subject to Principle III.
- **II. Zero-Subscription Cost**: unpacked extension ($0), no store fee,
  no signing, offline AI default. PASS.
- **III. API-First, Polite Ingestion / no bot bypass**: the extension
  automates nothing site-facing beyond form filling; it never bypasses
  bot protection (it runs as the user, in the user's session), never
  auto-submits, never clicks apply/submit/login. PASS.
- **IV. Reusable Core, Thin Web Layer**: engine/ never imports web/ — the
  bridge send-callable is injected by the web layer into ext_backend;
  extension JS holds zero business logic. PASS.
- **V. Tested Core Logic**: field_core/protocol/qa/backends all unit-
  tested; real-extension integration suite; offline gate extended. PASS.

## Project Structure

### Documentation (this feature)

```text
specs/010-copilot-release/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output (incl. live gate + walkthrough)
├── contracts/
│   ├── bridge-protocol.md   # WebSocket message contract app ↔ extension
│   └── http-api.md          # New/changed HTTP endpoints
└── tasks.md             # Phase 2 output (/speckit.tasks)
```

### Source Code (repository root)

```text
extension/                       # NEW — MV3 companion (plain JS, no build)
├── manifest.json                # MV3; storage/tabs/alarms; host_permissions
│                                # http://127.0.0.1/*; content <all_urls>,
│                                # all_frames:true; minimum_chrome_version 116
├── background/
│   ├── service-worker.js        # entry; wires modules
│   ├── socket.js                # connect/reconnect/backoff/keepalive(20s)
│   ├── protocol.js              # message constants + validation
│   ├── tabs.js                  # open/close/track tabs, frame routing
│   └── badge.js                 # connection badge
├── content/
│   ├── main.js                  # lifecycle, port to SW, orphan detection
│   ├── scanner.js               # serialize+stamp (SERIALIZE_JS parity),
│   │                            # MutationObserver 500ms + 2s safety poll
│   ├── filler.js                # native-setter fills, recheck, DataTransfer
│   │                            # files; NO .click() ANYWHERE
│   ├── overlay.js / overlay.css # slide-in shadow-DOM progress panel
├── popup/
│   ├── popup.html / popup.js    # status, Fill this page, recovery pairing
└── pairing.json                 # stamped by app at runtime (gitignored)

engine/autofill/
├── field_core.py                # NEW — transport-agnostic per-descriptor
│                                # decision logic extracted from
│                                # watcher._process_field (single source)
├── ext_backend.py               # NEW — extension session, command
│                                # translation, inbound message processing
├── ext_protocol.py              # NEW — pydantic message schemas
├── browser_controller.py        # CHANGED — backend field (auto|extension|
│                                # playwright), dispatch routing, ad-hoc
│                                # session, connectivity accessor
├── watcher.py                   # CHANGED — delegates rules to field_core
└── (worker.py, adapters.py, fields.py, apply_urls.py unchanged)

engine/
├── qa.py                        # NEW — grounded draft generation (concise
│                                # 60-120w), tier-aware, refusal on thin
│                                # grounding; sensitive tags excluded
├── answers.py                   # CHANGED — draft provenance (ai_draft →
│                                # confirmed | auto_saved), match-first rule
├── db.py                        # CHANGED — additive migrations: answers
│                                # provenance columns; applications
│                                # follow_up_at/notes; bridge_secret setting
└── settings.py                  # CHANGED — AUTOFILL_BACKEND default auto

web/
├── routes_bridge.py             # NEW — WebSocket /ws/ext, GET /api/bridge/info,
│                                # GET /api/bridge/file/<token> (one-time
│                                # resume fetch)
├── routes_autofill.py           # CHANGED — status gains extension{...} +
│                                # backend; drafts review endpoints
├── routes_api.py                # CHANGED — follow-ups CRUD, next-actions,
│                                # detected-submission confirm
├── main.py                      # CHANGED — bridge router, dashboard route,
│                                # companion walkthrough page
├── templates/                   # CHANGED — home dashboard, autofill screen,
│   │                            # tracker board, walkthrough + identity pass
│   └── partials/                # connection card, drafts list, next actions
└── static/styles.css            # CHANGED — single design-token layer
                                 # (CSS variables), light/dark

scripts/stamp_extension.py       # NEW — materialize extension/ into
                                 # <data_dir>/extension + stamp pairing.json
desktop.py                       # CHANGED — call stamp after port bind
packaging/{jobengine.spec,windows.iss,smoke_test.py}  # CHANGED — bundle
                                 # extension assets; smoke asserts bridge

tests/
├── test_ext_protocol.py         # NEW
├── test_field_core.py           # NEW (shared-rule suite, both backends)
├── test_ext_backend.py          # NEW (fake sender; secret redaction)
├── test_qa.py                   # NEW (grounding, refusal, length, sensitive)
├── test_routes_bridge.py        # NEW (auth, one-session, file token)
├── integration/test_extension_fixture_pages.py  # NEW — real extension via
│                                # --load-extension against fixture pages
├── fixtures/ats_pages/          # + react_controlled.html,
│                                # react_select_dropdown.html,
│                                # file_upload_input.html, essay_question.html
└── (existing suites updated where payloads/templates changed)
```

**Structure Decision**: single repo, existing layout preserved; the
extension is a new top-level `extension/` folder mirrored into the data
dir at runtime (the app owns and updates it — this is also the pairing
channel). No build toolchain for JS — plain ES modules keep the $0/no-
dependency constraint and PyInstaller packaging trivial.

## Key design decisions (full detail: research.md + design doc)

1. **Pairing via the extension folder itself**: app stamps
   `extension/pairing.json` = `{port, secret, app_id}` at every launch;
   unpacked extensions re-read packaged files from disk on every
   `fetch(chrome.runtime.getURL(...))` — no reload, no pairing UX.
   32-byte secret in first WS frame; wrong → close 4401.
2. **Descriptor parity**: scanner.js emits byte-identical descriptors to
   watcher.py's SERIALIZE_JS, so fields.py/adapters.py classify unchanged.
   Stamps as DOM attributes survive content-script reloads. Handled
   ledger stays in Python.
3. **One facade, two backends**: field decision rules extracted to
   field_core.py; ext_backend.py + worker/watcher both consume it.
   Backend chosen at start_queue (extension iff socket live <10s
   heartbeat), sticky per queue; disconnect → interrupted + explicit
   user choice. Report/status payloads byte-compatible.
4. **Ad-hoc mode**: "Fill this page" creates a job-less session keyed by
   tab; same rules/report; app offers tracker linkage (URL/title match to
   an existing job, else create).
5. **Secrets fill-and-forget**: value flows keyring→Python→WS→SW→content→
   DOM only for watched tabs on matching registrable domains; never
   stored/logged/echoed; masked `•••` in reports (unchanged).
6. **AI drafts**: qa.py generates only from resume/profile/answers/job
   fields; refuses on thin grounding (leave untouched → needs_manual).
   New outcome `ai_draft` joins the report vocabulary + overlay flag.
   Saved-answer matching always runs first. Sensitive tags
   (work-auth/visa/EEO) excluded at the classifier level (allowlist of
   AI-eligible tags, not a blocklist).
7. **Detected submission**: content script observes form submit events +
   confirmation-page URL/DOM heuristics; emits `page_event
   {kind:"submitted?"}`; app raises a user-confirmable "Mark as applied?"
   next-action and (on confirm) auto-saves final draft texts (FR-013b).
   Never silent.
8. **UI overhaul**: one design-token CSS layer (variables) + per-surface
   template rework; frontend-design skill at implementation time;
   existing accessibility tests remain the floor.

## Complexity Tracking

No constitution violations. New surface (extension) justified as the
primary user-requested capability; mitigated by zero-logic-in-JS and the
shared field_core.
