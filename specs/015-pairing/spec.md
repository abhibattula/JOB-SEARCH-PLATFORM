# Feature Specification: The Pairing Release

**Feature Branch**: `015-pairing`
**Created**: 2026-07-25
**Status**: Draft
**Input**: User description: "Rebuild the Apply Assist companion pairing/connection/diagnostics layer and harden the on-device AI runtime, keeping the proven fill core unchanged. Driven by machine-verified root causes: a native AI-runtime crash closed the app, on-device AI calls race and freeze the UI, companion pairing has never succeeded and fails silently at every step, the OS default browser (Edge) contradicts the user's intent (Chrome) with no override, plus session-path bugs (answer-confirm error, updater failures, installer hoard)."

## Clarifications

### Session 2026-07-25

- Q: How bulletproof should the AI-crash fix be? → A: **D1 — serialize all
  on-device AI behind a single owner now (locks + one worker); run a time-boxed
  process-isolation spike with an explicit go/no-go (GO = packaged-build gate
  passes on Windows and macOS CI). The release never blocks on the spike.**
- Q: What happens when Apply Assist starts without a connected companion? →
  A: **D2 — proceed in the assistant window with a loud, persistent notice
  naming the actual path ("assistant window — Edge/Chrome, not signed in") and
  a connect link. Never block the user.**
- Q: Default for the new preferred-browser setting? → A: **D3 — default
  Chrome (options: Chrome / Edge / Auto = OS default). A live companion always
  wins regardless of preference; OS-default vs preference mismatch is always
  surfaced with a one-click jump to the OS default-apps settings.**

## User Scenarios & Testing *(mandatory)*

### User Story 1 - The app never crashes or freezes because of on-device AI (Priority: P1)

Whatever combination of features is running — filling an application while the
feed refreshes, drafting an answer while a resume imports — the app stays alive
and responsive. Status panels keep updating while an AI suggestion is being
generated, a still-generating suggestion shows as "drafting…" and fills in when
ready, and if the app ever did end abnormally, the next launch says so instead
of pretending nothing happened.

**Why this priority**: A crash or freeze invalidates every other feature. The
recorded hard crash (native fault in the AI runtime) and the built-in freeze
(AI generation blocking the status view) are the two defects that made every
prior version feel broken; nothing else in this release matters if the app can
still die mid-application.

**Independent Test**: Run many AI-consuming features concurrently (scoring,
drafting, suggesting, importing) and confirm the app survives with all results
correct; start a slow suggestion and confirm the Apply Assist status view keeps
responding; force an abnormal end and confirm the next launch shows the notice.

**Acceptance Scenarios**:

1. **Given** several features request on-device AI at the same time, **When**
   they run, **Then** the work completes one-at-a-time with no crash and every
   caller receives its result or a clean failure.
2. **Given** an AI suggestion is generating for a paused question, **When** the
   user watches the Apply Assist screen, **Then** status updates keep arriving
   (within 1 second per refresh) and the question shows "drafting…" until the
   suggestion appears in place.
3. **Given** the previous app session ended without a clean shutdown, **When**
   the app next launches, **Then** a one-time notice says so and links to
   diagnostics.
4. **Given** the process-isolation spike is a GO, **When** an AI-runtime fault
   is forced mid-generation, **Then** the app stays open, reports the fault,
   and the next AI request works again. *(Spike-conditional — the release does
   not block on this scenario.)*

---

### User Story 2 - Pair once, see it verified, never wonder again (Priority: P2)

The user opens "Connect your browser", follows the steps, and watches each step
verify itself live: the app confirms its own setup is good, then shows the
companion connecting, then shows "Connected — Chrome (companion v1.5.0)". If
anything is wrong at any layer — the app couldn't prepare the pairing files,
the wrong folder was loaded, the app was restarted and the companion is being
rejected — the exact problem and its fix are stated where the user is looking
(the connect page and the companion's own popup). Starting a fill session
always states which path it will use; when the companion isn't connected, the
session proceeds in the assistant window with a loud notice and a connect link.

**Why this priority**: Pairing has never once succeeded on the primary user's
machine, and every failure along the chain was silent — this is the release's
namesake and the reason Apply Assist "never worked". It is second only to
stability because an unstable app makes even perfect pairing moot.

**Independent Test**: On a machine without the companion, walk the connect
wizard and confirm each failure state is truthfully described (app setup
failure banner, not-installed guidance, rejected-connection troubleshooting);
load the companion in Chrome and in Edge and confirm the wizard reaches
"Connected" with the right browser name; start a queue with and without the
companion and confirm the stated fill path matches reality.

**Acceptance Scenarios**:

1. **Given** the app prepares pairing at launch, **When** that preparation
   fails for any reason, **Then** a visible notice appears in the app the same
   session (Apply Assist + connect pages) stating the failure — never
   log-only.
2. **Given** the companion is loaded in a supported browser while the app
   runs, **When** the user watches the connect page, **Then** it reaches
   "Connected" within 60 seconds and names the browser and companion version.
3. **Given** the companion cannot connect (app closed, pairing stale, wrong
   folder, version mismatch), **When** the user opens the companion's popup,
   **Then** it states the specific reason in plain language and offers a
   retry — and its "Fill this page" control explains why it can't act instead
   of doing nothing.
4. **Given** a fill session starts without a connected companion, **When** the
   queue begins, **Then** it proceeds in the assistant window AND the Apply
   Assist screen shows a persistent, prominent notice: the actual path
   ("assistant window — Edge/Chrome, not signed in") plus a connect link.
5. **Given** any active fill session, **When** the user looks at the Apply
   Assist screen, **Then** it states the active path: "your own browser
   (companion — Chrome)" or "assistant window (Edge — not signed in)".
6. **Given** the diagnostics view, **When** opened, **Then** it reports the
   whole chain in one place: setup outcome, pairing freshness and port match,
   companion connection (browser, version, heartbeat age), recent rejected
   connection attempts, OS default browser, and the user's preference.

---

### User Story 3 - Links open in the browser I chose (Priority: P3)

The user picks a preferred browser (default: Chrome). Job links and the
assistant window use it. When Windows' own default contradicts the preference,
the app says so plainly and offers a one-click jump to the OS setting to fix
it — no more silent Edge surprises.

**Why this priority**: The "why is everything Edge?" confusion triggered the
whole investigation, but it only misleads — it doesn't crash or block. With
pairing transparent (US2), the wrong-browser sting is already reduced.

**Independent Test**: Set the preference to each value and confirm job links
and the assistant window honor it (with graceful fallback when the preferred
browser is missing); create an OS-default/preference mismatch and confirm the
mismatch line and the one-click fix appear.

**Acceptance Scenarios**:

1. **Given** the preference is Chrome (default), **When** a job link is opened
   or the assistant window launches, **Then** Chrome is used when installed —
   even if the OS default is Edge; if Chrome is missing, the OS default is
   used and the substitution is noted.
2. **Given** a connected companion, **When** a fill session starts, **Then**
   the companion's browser is used regardless of the preference.
3. **Given** the OS default differs from the preference, **When** the user
   views Apply Assist or the connect page, **Then** a mismatch line shows both
   values and (on Windows) a control opens the OS default-apps settings
   directly.

---

### User Story 4 - The rough edges are gone (Priority: P4)

Confirming an answer during a practice or ad-hoc fill session saves cleanly
instead of erroring. A failed update download ends in a clear message — never
a background crash — and old downloaded installers stop accumulating.

**Why this priority**: Real, evidenced bugs the user hit, but each is narrow;
they polish the same journeys the bigger stories fix.

**Independent Test**: Confirm an answer during a practice session and verify
success; simulate an empty/corrupt update download and a locked leftover file
and verify clean messages, no crash, and that old installers are pruned.

**Acceptance Scenarios**:

1. **Given** a practice or ad-hoc fill session, **When** the user confirms a
   paused question's answer, **Then** it saves and the session continues (no
   server error), and the answer is reusable later.
2. **Given** an update download that arrives empty or incomplete, **When**
   verification runs, **Then** the user sees a clear failure message, nothing
   crashes, and a retry is possible.
3. **Given** leftover update files that are temporarily locked, **When**
   cleanup runs, **Then** it defers safely (no error) and completes on a later
   launch; at most the newest previous installer is retained.

---

### Edge Cases

- **App restarted (new session) while the companion still holds old pairing
  data**: the companion re-reads pairing on every attempt and recovers on its
  next retry/watchdog tick; the connect page reflects the brief gap truthfully.
- **The app's port is taken by another process at next launch**: pairing is
  re-stamped with the new port; diagnostics flags any mismatch between the
  pairing record and the live port.
- **Companion loaded from the wrong folder** (no pairing file): it can never
  connect; the popup says "pairing file missing — load the folder shown in the
  app", and the connect page's troubleshooting covers it.
- **Extension removed or its browser closed mid-queue**: the existing
  interrupted-session handling applies; the stated fill path updates on the
  next status refresh.
- **Companion connects mid-queue**: the running queue keeps its chosen path
  (sticky per run, unchanged rule); the next queue uses the companion; the
  path indicator stays truthful throughout.
- **Preferred browser uninstalled**: fall back to the OS default with a visible
  note; never fail the open.
- **AI generation exceeds its time budget**: the request fails cleanly; the
  affected field is reported as needs-manual; the session continues.
- **Both stability and pairing failures at once** (e.g., setup failed AND AI
  busy): notices coexist without obscuring each other; diagnostics shows both.

## Requirements *(mandatory)*

### Functional Requirements

**Stability (US1)**

- **FR-001**: All on-device AI work MUST execute strictly one-at-a-time
  (serialized), regardless of how many features request it concurrently, and
  every caller MUST receive its result or a clean failure. "All" means every
  caller path without exception: match scoring, answer drafting, answer
  suggestions, resume tailoring, profile import/extraction, and embeddings.
- **FR-001a**: When more simultaneous AI requests arrive than the system will
  hold, the excess requests MUST fail immediately and cleanly (the same
  failure class callers already tolerate) — never unbounded waiting.
- **FR-002**: No status/read view may wait behind AI generation: the Apply
  Assist status view MUST keep responding (within 1 second per refresh) while
  any AI draft/suggestion is generating.
- **FR-003**: A paused question whose suggestion is still generating MUST be
  shown immediately (marked "drafting…") and update in place when the
  suggestion is ready — the pause never waits for the AI to finish.
- **FR-004**: On-device AI requests MUST have a time budget; exceeding it MUST
  yield a clean failure that callers already tolerate (field reported
  needs-manual; scoring skipped), never a hang.
- **FR-005**: The app MUST detect an abnormal previous end (no clean shutdown)
  and show a one-time notice on next launch linking to diagnostics.
- **FR-006** *(spike-conditional, D1)*: If the process-isolation spike is GO,
  a fault in the AI runtime MUST NOT close the app: the fault is contained,
  reported, and the next AI request works. GO/NO-GO is decided solely by the
  packaged-build gate passing on both supported OSes; the release proceeds
  either way.

**Pairing & transparency (US2)**

- **FR-007**: At every launch the app MUST prepare pairing (materialize
  companion files + write the pairing record), MUST verify the result by
  reading it back, and MUST record the outcome (success, or the exact failure
  reason and time).
- **FR-008**: A pairing-preparation failure MUST produce a visible in-app
  notice the same session on the Apply Assist and connect pages — never
  log-only.
- **FR-009**: Pairing preparation MUST NOT depend on any component beyond the
  minimum needed to copy files and write the pairing record; an automated
  guard MUST enforce this so the shipped failure class (a heavyweight optional
  component breaking pairing) cannot recur.
- **FR-010**: The connect page MUST verify live, per step: app preparation OK
  → companion installed/authenticating → connected (browser name + companion
  version shown), with troubleshooting mapped to the actual observed failure
  (including rejected-connection kinds: bad secret vs version mismatch).
- **FR-011**: The companion's popup MUST always state its condition in plain
  language — connected (to which app port), or the specific reason it is not
  (app not running, pairing file missing, connection rejected: stale pairing /
  version mismatch) — and MUST offer a manual retry. Its "Fill this page"
  control MUST explain why it can't act when disconnected instead of silently
  doing nothing.
- **FR-012**: Starting a fill session without a connected companion MUST
  proceed in the assistant window AND show a persistent, prominent notice
  naming the actual path ("assistant window — Edge/Chrome, not signed in")
  with a connect link (D2). The user is never blocked.
- **FR-013**: The Apply Assist screen MUST always state the active fill path:
  the user's own browser via companion (naming the browser) or the assistant
  window (naming the browser and that it is not signed in).
- **FR-014**: A single diagnostics view MUST report the full chain: pairing
  preparation outcome, pairing record freshness and port match, companion
  connection state (browser, version, heartbeat age), counts/recency of
  rejected connection attempts by kind, OS default browser, and the browser
  preference. The pairing secret MUST NEVER appear on any diagnostic surface
  (doctor, wizard, popup, banners, logs) — diagnostics report facts about the
  secret (set/accepted/rejected), never the value.
- **FR-015**: The companion MUST report a version that tracks the app release
  that prepared it, so "connected — companion vX" is meaningful.

**Browser intent (US3)**

- **FR-016**: A browser preference setting MUST exist with values Chrome /
  Edge / Auto (OS default), defaulting to Chrome (D3), editable in Settings.
- **FR-017**: Opening job links and launching the assistant window MUST honor
  the preference; when the preferred browser is not installed, the OS default
  MUST be used and the substitution noted.
- **FR-018**: A connected companion MUST always take precedence over the
  preference and the OS default for fill sessions.
- **FR-019**: When the OS default browser differs from an explicit preference
  (Chrome or Edge), the mismatch MUST be shown (both values) on the Apply
  Assist and connect pages. With the preference set to Auto no mismatch is
  possible by definition (Auto IS the OS default) and none is shown. The
  one-click control that opens the OS default-apps settings is Windows-only;
  on other platforms the mismatch line appears without it.

**Rough edges (US4)**

- **FR-020**: Confirming a paused question's answer during practice or ad-hoc
  sessions MUST succeed: the answer is saved for reuse, no per-application
  snapshot row is recorded for sessions that are not a tracked job, and the
  session continues.
- **FR-021**: The updater MUST reject an empty or incomplete download before
  verification with a clear user-facing failure; cleanup of locked files MUST
  defer safely (never crash a background thread) and complete on a later
  launch.
- **FR-022**: Downloaded installers MUST be pruned so that at most the newest
  previous installer is retained alongside any current download.

### Key Entities

- **Pairing Record**: what the companion reads to find and authenticate to the
  app — port, secret reference, protocol generation, prepared-at time.
- **Pairing Preparation Outcome**: success/failure, exact reason, time, port —
  the source for banners and diagnostics.
- **Companion Session**: live connection state — connected, companion version,
  browser name, last-heartbeat age; plus counters of recent rejected attempts
  by kind (authentication vs version).
- **Fill Path Disclosure**: the truthful statement of where filling happens —
  companion (browser name) or assistant window (browser name, signed-out).
- **Browser Preference**: Chrome / Edge / Auto, default Chrome.
- **Update Artifact**: a downloaded installer and its lifecycle — verified,
  failed (reason), pending-cleanup, pruned.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: An 8-way concurrent on-device AI stress run completes with
  strictly serial execution, zero crashes, and all callers receiving results
  or clean failures (automated).
- **SC-002**: While a slow AI suggestion generates, the Apply Assist status
  view answers every refresh within 1 second (automated regression; previously
  it could hang for minutes).
- **SC-003**: 100% of pairing-preparation failures produce a visible in-app
  notice in the same session (verified by fault injection); zero log-only
  failures.
- **SC-004**: With the companion loaded and the app running, the connect page
  reaches "Connected" (correct browser name) within 60 seconds — verified
  end-to-end in BOTH Chrome and Edge by the automated real-browser suite,
  exercising the real preparation step.
- **SC-005**: The packaged-build gate fails if pairing preparation did not run
  and verify in that very launch (the shipped silent-failure class can no
  longer ship).
- **SC-006**: 100% of fill-session starts state the active path (companion +
  browser, or assistant window + browser); starting without a companion always
  shows the D2 notice with a connect link.
- **SC-007**: The companion popup never presents a dead control: in every
  disconnected state it names the reason and offers a retry (state-by-state
  automated checks).
- **SC-008**: Confirming answers during practice/ad-hoc sessions succeeds in
  100% of attempts (previously: server error).
- **SC-009**: Simulated update failures (empty download, corrupt download,
  locked leftover file) all end in a clear user-facing message with zero
  background crashes; stored installers never exceed current + newest previous.
- **SC-010**: An OS-default vs preference mismatch is visible on the relevant
  screens in the same session it arises, with the one-click OS-settings
  control present on Windows.
- **SC-011** *(spike-conditional)*: If isolation is GO — a forced AI-runtime
  fault mid-generation leaves the app running, shows a contained-fault notice,
  and the next AI request succeeds.

## Assumptions

- Chrome and/or Edge is installed; the companion remains a locally-loaded
  (unpacked) extension — the $0, no-store distribution is unchanged.
- The localhost trust model for the companion bridge is unchanged from 010
  (secret presented to the local app after an identity probe); hardening it
  further is out of scope.
- The proven fill core (field detection/classification/filling, click guards,
  ATS adapters) is correct and untouched except where value resolution must
  stop blocking on AI.
- Windows is the primary environment (all root-cause evidence is Windows);
  macOS behavior is verified via the existing CI gate.
- Existing sticky-per-run backend choice, never-auto-submit, and
  secrets-fill-and-forget rules all carry forward unchanged.
- The subprocess-isolation spike is time-boxed; its NO-GO path (serialized
  owner only) is a fully acceptable release state (D1).
