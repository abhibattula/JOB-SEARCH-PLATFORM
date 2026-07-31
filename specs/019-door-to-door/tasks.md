# Tasks: Door to Door

**Input**: Design documents from `/specs/019-door-to-door/`
**Prerequisites**: plan.md, spec.md, research.md (R1-R25), data-model.md,
contracts/escort-protocol.md, contracts/escort-ui.md, checklists/ (both complete)

**Tests**: REQUIRED — hybrid speckit + superpowers TDD. Every task pair is
red-then-green: the "Failing tests" task MUST be written and observed to fail
before its implementation task starts. Every new interactive control gets a
real-browser click test asserting its observable effect (018 lesson — no
string-presence-only coverage for controls).

**Organization**: grouped by user story (spec.md priorities P1-P5), sequential
delivery, each story independently testable and shippable.

## Format: `[ID] [P?] [Story] Description`

---

## Phase 1: Setup

- [x] T001 Baseline evidence: run the full unit battery and `-m browser`
      suite on branch tip pre-change; record counts in
      specs/019-door-to-door/baseline.txt

---

## Phase 2: Foundational (blocks all user stories)

- [x] T002 [P] Failing tests tests/test_ext_protocol.py::TestEscortProtocol019 +
      ::TestCompat019 — additive `Descriptor.form_context` (default "");
      new `CredentialSave`, `AdvanceStep` (outbound, carries `step_key`),
      `AdvanceResult` (inbound) models; PROTOCOL_V still 1; v1.8-shaped
      messages still validate; unknown fields ignored
- [x] T003 engine/autofill/ext_protocol.py: implement the additive models and
      register them (inbound/outbound maps) — T002 green

**Checkpoint**: protocol speaks 019 additively; nothing user-visible changed

---

## Phase 3: User Story 1 — The companion never lies about its state (P1) 🎯 MVP

**Goal**: version skew visible everywhere and never silently drops work;
Apply-here fills the pressed tab; fill-here supersedes stale sessions; file
tokens survive retries; arming survives worker restarts.

**Independent Test**: stale-bundle run shows amber on all three surfaces;
apply-here browser test asserts tab count unchanged + a field actually filled.

- [x] T004 [P] [US1] Failing unit tests/test_ext_backend.py::TestVersionSkew019 —
      mismatched hello version ⇒ radio decisions become visible `needs_manual`
      reason `version_mismatch` + doctor counter `version_mismatch_fills`
      (today: silent drop); escort arming refused on mismatch (FR-035)
- [x] T005 [US1] engine/autofill/ext_backend.py + engine/autofill/page_answers.py:
      replace the silent radio drop; surface the reason; add the doctor
      counter — T004 green
- [x] T006 [P] [US1] Failing asset+browser tests
      (tests/test_extension_assets.py::TestVersionSkewAssets019;
      tests/integration/test_companion_widget.py::TestVersionSkew019) —
      socket.js persists {appVersion, mismatch} from hello_ok; popup and
      panel render the reload notice; companion.html renders amber on
      mismatch (patched app_version in the live app)
- [x] T007 [US1] extension/background/socket.js + service-worker.js +
      extension/popup/ + extension/content/panel.js: read/compare/persist/
      render the mismatch state — T006 green (extension side)
- [x] T008 [US1] web/main.py + web/templates/companion.html: server-side
      compare of the hello version; amber state + copy — T006 green (app side)
- [x] T009 [P] [US1] Failing unit tests/test_browser_controller.py +
      tests/test_ext_backend.py — `start_queue(job_ids, adopt_tab_id=…)`
      skips open_tab and seeds the watch; `_handle_tab_opened` never
      overwrites an adopted watch
- [x] T010 [US1] engine/autofill/browser_controller.py + ext_backend.py:
      adopt-current-tab path; `_handle_apply_here` passes the tab — T009 green
- [x] T011 [US1] Strengthen browser test
      tests/integration/test_companion_widget.py apply-here: assert tab count
      unchanged AND ≥1 field filled in the original tab (red on old behavior,
      green after T010)
- [x] T012 [P] [US1] Failing unit — `fill_here` supersedes a finished/
      abandoned session; `busy` only while another tab is actively mid-fill
      and the refusal names that tab (FR-004)
- [x] T013 [US1] ext_backend.py `_handle_fill_here` supersede logic — T012 green
- [x] T014 [P] [US1] Failing unit — file token redeemable more than once
      within TTL; expires at TTL; invalidated on session end (FR-005)
- [x] T015 [US1] ext_backend.py token mark-used-within-TTL — T014 green
- [x] T016 [P] [US1] Failing browser test — kill/restart the MV3 service
      worker mid-session (CDP), assert the opener stays armed
      (`adhoc:false` restored via persisted jobId)
- [x] T017 [US1] extension/background/tabs.js persist jobId;
      service-worker.js adhoc recompute — T016 green
- [ ] T018 [US1] Checkpoint: full unit battery + `-m browser` green; commit

---

## Phase 4: User Story 2 — Real application forms actually fill (P2)

**Goal**: labels via the full ladder, shadow DOM traversal, Workday menus,
placeholder selects, fixed-position visibility, guard overreach fix, opener
refresh with the shared step-key.

**Independent Test**: each new fixture fills end-to-end in a real browser.

- [x] T019 [P] [US2] Fixture tests/fixtures/ats_pages/aria_labelledby.html
      (fields labelled ONLY via aria-labelledby, incl. a div[role=combobox])
- [x] T020 [P] [US2] Fixture tests/fixtures/ats_pages/shadow_form.html
      (whole form inside an open shadow root; options in the root too)
- [x] T021 [P] [US2] Fixture tests/fixtures/ats_pages/workday_prompt_options.html
      ([data-automation-id=promptOption] menu + extended automation-id fields)
- [x] T022 [P] [US2] Fixture tests/fixtures/ats_pages/placeholder_select.html
      (<option value="0">Select…</option> + custom-widget placeholder text)
- [x] T023 [P] [US2] Fixture tests/fixtures/ats_pages/fixed_modal_form.html
      (form inside a position:fixed dialog)
- [x] T024 [P] [US2] Fixtures tests/fixtures/ats_pages/greenhouse_navigate_apply.html
      → greenhouse_application_target.html (Apply link that NAVIGATES)
- [x] T025 [P] [US2] Failing tests — browser: aria_labelledby fixture
      question captured + field fills; unit tests/test_fields.py rows:
      automation_id joins the classifier haystack
- [x] T026 [US2] extension/content/scanner.js labelText ladder
      (labels → aria-label → aria-labelledby → ancestor label → preceding
      sibling); engine/autofill/watcher.py SERIALIZE_JS parity;
      engine/autofill/fields.py haystack — T025 green
- [x] T027 [P] [US2] Failing browser test — shadow_form: probe > 0, widget
      appears, fields fill (today: nothing renders at all)
- [x] T028 [US2] scanner.js `deepQueryAll()` (open roots, depth-capped) used
      by probe/serialize; filler.js option harvest via deepQueryAll;
      opener.js lookup — T027 green
- [x] T029 [P] [US2] Failing tests — browser: workday_prompt_options option
      chosen and verified; unit tests/test_adapters.py: expanded
      _WORKDAY_AUTOMATION (~20 keys)
- [x] T030 [US2] extension/content/filler.js harvest promptOption/menuItem;
      engine/autofill/adapters.py map growth — T029 green
- [x] T031 [P] [US2] Failing tests — unit tests/test_field_core.py
      placeholder-value rule table; browser: placeholder_select fixture
      fills (today: skipped_existing forever)
- [x] T032 [US2] Shared placeholder rule: scanner.js jeValue +
      engine/autofill/field_core.py decide + filler.js currentDisplayed —
      T031 green
- [x] T033 [P] [US2] Failing tests — browser: fixed_modal_form fields seen
      and filled; unit tests/test_watcher.py visibility rows
      (visibility:hidden false-positives die too)
- [x] T034 [US2] scanner.js + watcher.py visibility check (client rect +
      computed style; offsetParent no longer disqualifies fixed) — T033 green
- [x] T035 [P] [US2] Failing unit tests/test_click_guard.py own-name table —
      widget wrapper with "Next" in descendant text is fillable; a real Next
      button stays denied; JS/PY parity test stays green
- [x] T036 [US2] engine/autofill/click_guard.py + extension/content/click_guard.js
      own-name-for-allow judgment — T035 green; behavior tables updated
      consciously
- [ ] T037 [P] [US2] Failing tests — browser: greenhouse_navigate_apply
      clicks Apply, navigates, application page fills; unit: opener one-shot
      key is (doc token + control fingerprint), not href (SPA-safe)
- [ ] T038 [US2] extension/content/opener.js refreshed selectors
      (job-boards.greenhouse.io, navigating links) + step-keyed one-shot;
      engine/autofill/adapters.py APPLY_OPENERS additions; parity test —
      T037 green
- [ ] T039 [US2] Checkpoint: full unit battery + `-m browser` green; commit

---

## Phase 5: User Story 3 — Sign-in is handled (P3)

**Goal**: login walls become a first-class state; vault-backed credential
fill; one-shot state-gated Sign-in click; save-login-from-panel; registration
assist; secret hygiene proven.

**Independent Test**: login_wall fixture with a fake-keyring saved login is
crossed with zero manual clicks; without one, the widget offers the save form.

- [x] T040 [P] [US3] Fixtures tests/fixtures/ats_pages/login_wall.html
      (email/username + password + Sign in; post-login page) and
      registration.html (password + confirm + Create account)
- [ ] T041 [P] [US3] Failing unit tests/test_fields.py — login_email
      reachable via form_context; new login_username tag; registration
      context rows; watcher/scanner parity rows
- [ ] T042 [US3] scanner.js describe() emits form_context; watcher.py
      SERIALIZE_JS parity; engine/autofill/fields.py classify — T041 green
- [ ] T043 [P] [US3] Failing browser test — login_wall fixture: widget
      APPEARS in sign-in state (red today: probe hides it); without a vault
      entry it renders the save-login form
- [ ] T044 [US3] scanner.js probe reports login_wall (stops hiding password
      forms; application-form counts still exclude credential fields);
      extension/content/panel.js sign-in states per contracts/escort-ui.md —
      T043 green
- [ ] T045 [P] [US3] Failing unit — `prefilled_ok` terminal outcome for
      credential fields; sign-in arming requires BOTH engine-issued fills
      `filled`/`prefilled_ok` in that frame; once per doc token; failed
      sign-in (new doc, same wall) does NOT re-arm (FR-016, R15/R16)
- [ ] T046 [US3] engine/autofill/field_core.py prefilled_ok;
      engine/autofill/escort.py (new) sign-in arming state; ext_backend
      wiring — T045 green
- [ ] T047 [P] [US3] Failing unit — credential_save handler: saves via fake
      keyring backend, ack carries no secret/email, captured logs clean,
      re-arms sign-in for the reporting tab (FR-017)
- [ ] T048 [US3] ext_backend.py credential_save handler with redaction;
      panel.js save-form submit + immediate input clear — T047 green
- [ ] T049 [P] [US3] Failing browser test — full sign-in journey on
      login_wall with a fake-keyring saved login: both fields fill AND the
      Sign in control is actually clicked (observable navigation), exactly
      once
- [ ] T050 [US3] extension/content/advancer.js (sign_in kind only):
      allowlisted single guarded click site with its own asset pin;
      manifest.json content_scripts order; service-worker advance_step
      routing; engine dispatch — T049 green
- [ ] T051 [P] [US3] Failing tests — unit: credentials.generate_password
      properties (length/classes/no-ambiguous); browser: registration
      fixture — both password fields fill, credential saved to fake vault at
      fill time, Create account NOT clicked, needs-you prompt shown
- [ ] T052 [US3] engine/credentials.py generate_password; ext_backend
      registration flow; page_answers.py no_saved_login + prompts —
      T051 green
- [ ] T053 [US3] tests/test_secret_hygiene.py — instrumented full credential
      browser run; self-check that the scanner detects a planted canary
      leak, then assert DB/logs/chrome.storage/feed/doctor/artifacts are
      clean of the test password
- [ ] T054 [US3] Checkpoint: full unit battery + `-m browser` +
      secret-hygiene green; commit

---

## Phase 6: User Story 4 — Escorted to the door (P4)

**Goal**: engine-owned completeness predicate, full advancer (open_apply /
next), final-class layer, CAPTCHA pause, ready-for-review, cap, attribution,
LinkedIn refusal, flagship end-to-end suite.

**Independent Test**: one press on the wizard fixture set escorts posting →
sign-in → two filled steps → parked at review with Submit provably unclicked.

- [x] T055 [P] [US4] Fixtures tests/fixtures/ats_pages/wizard_multipage/
      (step1.html → step2.html → review.html with real navigation, Continue
      buttons type=submit, final Review-and-Submit sentinel)
- [x] T056 [P] [US4] Fixtures wizard_spa.html (same URL, DOM-swapped steps),
      wizard_loop.html (never-ending steps, for the cap), captcha_frame.html
      (stub recaptcha-style iframe)
- [ ] T057 [P] [US4] Failing unit tables tests/test_escort.py — completeness
      predicate truth table (required/in-flight/needs-you/focused/quiet
      ~2 s per research R19); one-shot per step_key; cap 12 ⇒ paused_cap;
      `advance_result not_found` on a complete step ⇒ your-turn pause
      (FR-024); attribution-window verdicts; state transitions incl.
      CAPTCHA-outranks-completeness; LinkedIn / mismatch / setting-off gates
      never arm
- [ ] T058 [US4] engine/autofill/escort.py full module (pure logic, no I/O) —
      T057 green
- [ ] T059 [P] [US4] Failing unit — ext_backend issues advance_step from the
      scan path when the predicate fires; advance_result lands in the
      Progression Click Record trail (fill report); submit_detected inside an
      attribution window excluded from _pending_submissions; overlay summary
      carries the new session states
- [ ] T060 [US4] ext_backend.py + browser_controller.py wiring (report trail,
      states, `escort_enabled` setting read) — T059 green
- [ ] T061 [P] [US4] Failing tests — unit: adapters.ADVANCE_ALLOWLIST
      (Workday bottom-navigation-next etc.) + advancer.js parity;
      FINAL_TERMS layer in both guard files (tests/test_click_guard.py new
      tables: progression-vs-final precedence, "Continue »" advance allowed
      for the advancer while final phrasings refuse); advancer single-click
      asset pin; LinkedIn domain refusal
- [ ] T062 [US4] engine/autofill/adapters.py ADVANCE_ALLOWLIST;
      engine/autofill/click_guard.py + extension/content/click_guard.js
      FINAL_TERMS; advancer.js `next` kind with generic fallback and
      final-class refusal (open_apply stays OPENER-owned per analyze finding
      A1 — opener reports its click via advance_result into the trail) —
      T061 green
- [ ] T063 [P] [US4] Failing browser test — captcha_frame: your_turn_captcha
      state shown, ZERO interactions with the frame, resume after the stub
      is removed and the page progresses
- [ ] T064 [US4] scanner.js captcha_present detection; escort precedence —
      T063 green
- [ ] T065 [P] [US4] Failing browser tests — panel states per
      contracts/escort-ui.md: ready_for_review park on review.html with the
      Submit sentinel PROVING no click; paused_cap at 12 on wizard_loop;
      needs-you pause expands the card and answering resumes; "Pause escort"
      stops advances while filling continues
- [ ] T066 [US4] panel.js state rendering + session_control pause_escort —
      T065 green
- [ ] T067 [US4] Flagship tests/integration/test_escort.py end-to-end:
      posting → opener Apply click → login_wall (fake vault) → sign_in →
      step1 fills → next → step2 fills (Workday options + placeholder
      select) → next → parked at review; trail (incl. the opener's
      open_apply result) visible in the Apply Assist record (test_web
      assertion); _pending_submissions stays empty throughout; plus a
      linkedin-domain fixture leg asserting ZERO clicks while filling stays
      active (FR-033 / US4-AS7)
- [ ] T068 [US4] Settings `escort_enabled` toggle (web/templates/settings.html
      + engine setting) with browser assert: OFF ⇒ exactly v1.8.0 fill-only;
      worker-restart browser test: advance count survives (cap cannot reset)
- [ ] T069 [US4] Checkpoint: full unit battery + `-m browser` green; commit

---

## Phase 7: User Story 5 — The promises match the product (P5) + Ship

- [ ] T070 [P] [US5] Update every pinned promise atomically with its test:
      extension/manifest.json description; panel.js footer ("You press the
      final Submit — never us.") + tests/test_extension_assets.py pin;
      activity messages in browser_controller.py + ext_backend.py;
      tests/test_browser_controller.py advance-is-user-driven reworded to
      Playwright-path-only
- [ ] T071 [P] [US5] Supersession notes: specs/018-companion/contracts/
      companion-ui.md footer line points at 019 contract;
      specs/005-apply-assist/spec.md FR-008 annotated superseded-in-part by
      constitution v1.2.0 (history preserved, not rewritten)
- [ ] T072 [P] [US5] Docs: web/main.py WHATS_NEW["1.9.0"];
      docs/USER_MANUAL.md (escort section + saved-logins consent);
      docs/USER_GUIDE.md; README.md ("Using it (v1.9)")
- [ ] T073 [US5] Version bumps: engine/__init__.py APP_VERSION,
      extension/manifest.json, packaging/windows.iss (byte-safe edit)
- [ ] T074 [US5] Full battery ×2 (flake check) + `-m browser` + slow markers
- [ ] T075 [US5] Frozen smoke (packaging/smoke_test.py) incl. keyring backend
      pinning frozen + version-skew amber against a stale 1.8.0 bundle
- [ ] T076 [US5] Manual quickstart.md §3-§5 against real Workday (account
      wall → escort → review STOP), real Greenhouse navigate-apply, and a
      LinkedIn zero-click control — user-assisted
- [ ] T077 [US5] Tag v1.9.0; verify BOTH installers (magic bytes + SHA-256
      vs release body); sync mirror branch; update auto-memory

---

## Dependencies & Execution Order

- Setup (T001) → Foundational (T002-T003) → US1 (T004-T018) → US2
  (T019-T039) → US3 (T040-T054) → US4 (T055-T069) → US5 (T070-T077).
- Single-developer sequential delivery in priority order; each story ends in
  a green-suite checkpoint commit and is independently shippable.
- Hard cross-story dependencies: US3's sign-in click introduces advancer.js
  (sign_in kind) which US4 extends — T050 blocks T062. US2's deepQueryAll
  (T028) is used by advancer lookups (T050/T062). US4's escort.py extends the
  arming module created in T046.
- Within each story: fixtures first, then red tests, then green
  implementation — never the reverse.

## Parallel Opportunities

- All fixture tasks in a story ([P], e.g. T019-T024) are independent files.
- Red-test tasks marked [P] can be authored in parallel within their story;
  their green counterparts are sequential where they touch shared files
  (scanner.js, ext_backend.py).

## Implementation Strategy

US1 alone is a shippable MVP (it fixes the "still not filling" trust bugs
with zero new click policy). US2 makes real pages fill. US3+US4 deliver the
user's automation ask. US5 is the honesty layer and the ship gate — the
release is not taggable until T074-T076 pass, matching quickstart.md §5.
