# Tasks: The Pairing Release (feature 015, v1.5.0)

**Input**: Design documents from `/specs/015-pairing/`
**Prerequisites**: plan.md, spec.md (amended per checklists/quality.md),
research.md (R1–R13), data-model.md, contracts/, quickstart.md

**Tests**: REQUIRED (constitution V + superpowers TDD) — every deterministic
engine change lands red→green; the human pairing path gets real-browser E2E in
BOTH Edge and Chrome; the frozen smoke gate is extended so the shipped
silent-stamp-failure class can never ship again.

**Organization**: Setup → Foundational (bridge consts + inference owner core)
→ US1 stability → US2 pairing → US3 browser intent → US4 rough edges →
Verify/docs/ship.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: parallelizable (different files, no dependency on an incomplete task).

---

## Phase 1: Setup

- [x] T001 Bump version to **1.5.0** (`engine/__init__.py`,
  `packaging/windows.iss`, `extension/manifest.json`); `packaging/check_version.py`
  OK; add `WHATS_NEW["1.5.0"]` stub in `web/main.py`.

---

## Phase 2: Foundational (blocking prerequisites)

- [x] T002 [P] `engine/autofill/bridge_const.py` (NEW): `PROTOCOL_V = 1`,
  `APP_ID = "jobengine"`, stdlib-only; `engine/autofill/ext_protocol.py` imports
  the constants from it. Tests: values unchanged (protocol parity), and
  `bridge_const` imports nothing outside the stdlib.
- [x] T003 `engine/inference.py` (NEW, R1) — TDD: write
  `tests/test_inference.py` FIRST (stub-model factory seam; 8-thread hammer
  asserting max observed concurrency == 1; timeout → RuntimeError; full queue
  (maxsize 32) → immediate RuntimeError; result correctness under load), watch
  it fail, then implement the single-owner daemon worker + bounded queue +
  `run_chat`/`run_embed` with env-overridable budgets
  (`JOBS_AI_TIMEOUT_CHAT`=180, `JOBS_AI_TIMEOUT_EMBED`=30).

**Checkpoint**: serialization core proven under stress with stubs — no real
model loaded anywhere in the default suite.

---

## Phase 3: US1 — The app never crashes or freezes from on-device AI (P1)

- [x] T004 [US1] Reroute `engine/local_llm.py::chat` and
  `engine/semantic.py::embed` through `inference.run_chat/run_embed` (model
  loading moves onto the owner thread); public failure contracts unchanged
  (chat raises RuntimeError; embed returns None). Add a guard test asserting
  no module outside `engine/inference.py` touches a llama object directly
  (AST/grep over `engine/` for `create_chat_completion`/`create_embedding`).
- [x] T005 [US1] R3 park-then-draft — TDD: test FIRST that
  `/api/autofill/status` answers < 1 s while a (slow stub) suggestion
  generates, and that the parked pending carries `drafting=True` then gains
  `drafted_answer` (nonce prevents a stale draft landing on a new pending).
  Then rework `browser_controller._value_for_tag`: park immediately under
  `_lock`, generate via the inference owner OFF the lock, update the pending
  via nonce-checked callback. Render "drafting a suggestion…" in the pending
  panel (`web/templates/partials/autofill_status.html`).
- [x] T006 [P] [US1] `engine/lifecycle.py` (NEW, R9): `mark_running()` /
  `clear_running()` / `was_unclean()` + tests; wire into `desktop.py` (mark at
  start, clear on both clean-exit paths); on unclean start set
  `UNCLEAN_EXIT_AT`; one-time dismissible banner in `web/templates/base.html`
  (server-side inline, 014 CLS-safe pattern) + dismiss route clearing the key
  + web tests (banner iff key set; dismiss clears).
- [ ] T007 [US1] R2 subprocess spike (time-boxed: ONE working session — if
  the packaged gates aren't green by T024, NO-GO is the automatic outcome):
  `JOBS_AI_SUBPROCESS=1`
  routes the owner's execution to a spawned `multiprocessing` child over a
  Pipe (both models in-child); parent supervises (child death → in-flight
  request fails cleanly, `runtime_restarted` flag exposed, lazy restart);
  `multiprocessing.freeze_support()` first in `desktop.py`/`cli.py` main
  guards. Tests: kill-child → clean failure + next request works (stub-level).
  Record GO/NO-GO in `research.md` (GO = frozen Windows smoke + mac CI green
  with mode ON → default on; NO-GO → default off, findings recorded).

**Checkpoint**: hammer green, status responsive during drafting, unclean-exit
banner works — US1 independently shippable.

---

## Phase 4: US2 — Pair once, see it verified, never wonder again (P2)

- [x] T008 [US2] Stamp rework (R4/R13) — TDD in
  `tests/test_stamp_extension.py` FIRST: always-writes-pairing (even when the
  copy has problems and dest already populated), read-back verification
  (port/secret/protocol), `stamp_status.json` written on success AND failure
  (`ok/error/at/port/app_version/copy_warning`), staged `manifest.json`
  version == `APP_VERSION`, and an AST import-allowlist test for
  `scripts/stamp_extension.py` (`json/shutil/sys/argparse/pathlib/__future__/
  engine.paths/engine.db/engine.autofill.bridge_const` only). Then implement
  in `scripts/stamp_extension.py` (+ `desktop.py` except-path writes the
  failure status too).
- [x] T009 [P] [US2] Bridge additions (R5): `ext_protocol.Hello` gains
  OPTIONAL `browser` field (old hellos stay valid — test);
  `engine/autofill/ext_backend.py` stores `browser` in the session, exposes it
  in `status()`, and adds `record_reject(kind)` counters
  (auth/protocol/last) + tests.
- [x] T010 [US2] `web/routes_bridge.py`: call `ext_backend.record_reject` at
  the 4401/4426 close sites; add `GET /api/companion/doctor` per
  `contracts/http-api-additions.md` (stamp status file, pairing
  present/port/protocol/fresh-vs-process-start, port.txt match, companion
  incl. browser, rejects, browser prefs/mismatch). Tests: response shape,
  freshness/port logic against tmp files, and **secret never present** in the
  serialized response.
- [x] T011 [US2] Stamp-failure banner (FR-008): surface `stamp_status.ok ==
  false` as a prominent server-side inline banner on the Apply Assist page and
  connect page + web tests (banner iff failure recorded).
- [x] T012 [US2] Connect wizard rework (`web/templates/companion.html`, R5):
  live per-step verification driven by a 3 s doctor poll — app preparation
  (stamp) → companion detected/authenticating (rejects distinguish stale
  pairing vs version mismatch vs nothing-knocking) → connected (browser +
  companion version); troubleshooting mapped to observed state; copy-path
  kept. ALSO render the same doctor snapshot as a companion section on the
  diagnostics page (FR-014's human-readable "single diagnostics view", not
  just the JSON endpoint). Template/web tests for the state hooks + the
  diagnostics section.
- [x] T013 [US2] Extension diagnostics (R8): `extension/background/socket.js`
  records `lastAttempt {stage, port, code, at}` on every transition +
  mirrors to `chrome.storage.session`; `service-worker.js` `status?` reply
  includes it and handles `connect!`; `popup.js`/`popup.html` render
  state-specific plain-language reasons (4401/4426 mappings per
  `contracts/bridge-protocol-additions.md`), always offer "Connect now", and
  make "Fill this page" explain instead of no-op when disconnected. Extend
  `tests/test_extension_assets.py` static asserts (storage.session usage,
  connect! handler, 4401/4426 mapping strings, no secret in session storage).
- [x] T014 [US2] D2 disclosure (R7): `/api/autofill/queue` response gains
  `backend`; `queue_snapshot()["extension"]` gains `browser`;
  `partials/autofill_status.html` renders the persistent path banner —
  companion → "Filling in your <Browser> (companion v<ver>)", assistant →
  warning "Assistant window — <Channel> (not signed in)" + connect link.
  Web/template tests for both states.
- [ ] T015 [US2] Human-path E2E (R12, browser marker):
  `tests/integration/test_pairing_e2e.py` — fresh `JOBS_DATA_DIR` → real
  uvicorn (ephemeral port) → REAL `stamp_extension.stamp(port)` →
  `launch_persistent_context` loading the STAMPED folder, once
  `channel="msedge"` and once `channel="chrome"` (skip-if-unavailable) → poll
  doctor to `connected` with correct `browser` → one fixture fill through the
  full chain.

**Checkpoint**: wizard truthfully walks to green in both browsers; every
failure mode named where the user is looking — US2 independently shippable.

---

## Phase 5: US3 — Links open in the browser I chose (P3)

- [ ] T016 [US3] `PREFERRED_BROWSER` setting (default `chrome`, values
  chrome/msedge/auto) + Settings page control (`web/templates/settings.html`)
  + tests (default value; persisted change).
- [ ] T017 [US3] `engine/autofill/default_browser.py`:
  `effective_channel_order()` (preference-first; auto → OS-default-first) and
  `open_url(url)` (App Paths exe launch for explicit preference,
  `os.startfile`/`open` fallback, returns what it used);
  `browser_controller._channel_order()` switches to it. **013 lesson**: grep
  tests asserting the old order (`tests/test_browser_channel.py`,
  `test_default_browser.py`) and update them to pin the NEW contract
  explicitly (not the machine default). Tests cover preference-first,
  auto passthrough, missing-preferred fallback, AND an explicit FR-018
  regression: with a live companion, `_choose_backend` picks the extension
  regardless of `PREFERRED_BROWSER`.
- [ ] T018 [P] [US3] Web: `/api/open` uses `open_url` + returns `opened_with`;
  callers surface a substitution note via the existing toast pattern when
  `opened_with` differs from the preference (FR-017 "substitution noted" —
  never silent); NEW `POST /api/os/default-apps` (Windows-only 200, else 409);
  mismatch line (both values) + Windows-only fix button on
  `autofill.html`/`companion.html` (auto ⇒ never a mismatch — test). Web
  tests for all four.

**Checkpoint**: Chrome-by-default routing with truthful mismatch surfacing —
US3 independently shippable.

---

## Phase 6: US4 — Rough edges (P4)

- [ ] T019 [P] [US4] `confirm_answer` sentinel guard (R10) — TDD: regression
  test FIRST (practice/ad-hoc current job → POST confirm → 200, answer-bank
  row created, NO `application_answers` row), then guard
  `web/routes_autofill.py::confirm_answer` (snapshot only when
  `job_id > 0`).
- [ ] T020 [P] [US4] Updater hardening (R11) — TDD in `tests/test_updates.py`:
  empty/short download (< 10 MB) rejected BEFORE hashing with "download
  incomplete (N bytes)"; locked-file cleanup defers to
  `updates/cleanup.json` (thread never crashes) and drains on next
  `startup_check`; prune keeps current + at most newest previous installer.
  Then implement in `engine/updates.py`.

---

## Phase 7: Verify, docs, ship

- [ ] T021 Frozen gate extension (R12): `packaging/smoke_test.py` asserts
  `pairing.json` mtime ≥ app launch, pairing port == `port.txt`,
  `/api/bridge/info` OK, doctor `stamp.ok` true (plus existing checks).
- [ ] T022 Full battery: `pytest -q` ×2 + `-m browser` (incl. NEW pairing E2E)
  + `-m slow` green; manual quickstart.md walkthrough (wizard in Chrome AND
  Edge, D2 notice, mismatch line, unclean-exit banner); fix findings.
- [ ] T023 [P] Docs: USER_MANUAL §19 (connect wizard walkthrough +
  troubleshooting table from close-code mappings + preferred browser +
  stability/what-changed), README (Apply Assist pairing + preferred browser),
  `WHATS_NEW["1.5.0"]` filled.
- [ ] T024 Ship: spike GO/NO-GO finalized in research.md; frozen build +
  `packaging/smoke_test.py` PASS (absolute exe path); merge `015-pairing` →
  `main`, mirror `main:001-ai-job-engine`, tag `v1.5.0`; verify BOTH
  installers (exe `MZ` / dmg `78 01`) + SHA-256 vs release body.

---

## Dependencies & Execution Order

- T001 first; T002/T003 (Foundational) before their consumers.
- US1: T004 needs T003; T005 needs T004; T006 [P] independent; T007 needs T003
  (and its GO/NO-GO lands in T024).
- US2: T008 needs T002; T009 [P]; T010 needs T008+T009; T011 needs T008;
  T012 needs T010; T013 [P] (extension-side, after T009 defines Hello.browser);
  T014 needs T009; T015 needs T008+T010+T013.
- US3: T016 → T017 → T018. US4: T019/T020 [P] anytime after Setup.
- Phase 7 last: T021 needs T008+T010; T022 gates T024; T023 [P] with T022.

## Parallel Opportunities

- T002 ∥ T003 · T006 ∥ T004/T005 · T009 ∥ T008 · T013 ∥ T010–T012 ·
  T019 ∥ T020 ∥ US3 tasks · T023 ∥ T022.

## Implementation Strategy (MVP first)

MVP = Setup + Foundational + **US1** (the app that never dies/freezes) — then
**US2** (pairing you can see), which is the release's namesake. US3/US4 are
small, independent, and can land in any order after. Verify/ship last, with
the spike's GO/NO-GO decided by the frozen gates in T024.
