# Research: Door to Door (019)

Decisions consolidated from three code-exploration passes (credential path,
session/click machinery, real-site fill gaps) and the approved plan. Format:
Decision / Rationale / Alternatives considered.

## Trust layer

**R1 — Version skew surfaces on every surface, and never silently drops work.**
Decision: the extension compares `hello_ok.app_version` (already sent by
`web/routes_bridge.py`) to `chrome.runtime.getManifest().version`; mismatch
renders amber on the app connect page, the popup, and the panel with
"Reload the companion at chrome://extensions". The silent radio drop in
`ext_backend.py` (~:626-635) becomes a visible `needs_manual` with reason
`version_mismatch` plus a doctor counter.
Rationale: after an app upgrade Chrome keeps running the old bundle until ↻;
today the app shows a green tick regardless, and radio fills vanish with zero
signal — the highest-probability cause of "still not filling".
Alternatives: hard-refuse the session on mismatch (rejected: an old companion
can still fill text fields — degrade visibly, not brutally); auto-reload the
extension (impossible from a content script for unpacked extensions).

**R2 — Apply-here adopts the current tab; open_tab is skipped.**
Decision: `bc.start_queue(job_ids, adopt_tab_id=…)`; when adopting, the
engine seeds `_watch` directly and never sends `open_tab`;
`_handle_tab_opened` must not overwrite an adopted watch.
Rationale: shipped v1.8.0 bug — `_handle_apply_here` sets the watch to the
user's tab, then the queued `open_tab`/`tab_opened` path overwrites it to a
duplicate tab; the user's tab strands on "filling".
Alternatives: close the duplicate after opening (rejected: flicker, race,
still steals focus); special-case in the extension (rejected: policy belongs
in the engine, Principle IV).

**R3 — `fill_here` supersedes stale sessions instead of refusing.**
Decision: if the running session's watch is finished/abandoned or targets
another tab with nothing in flight, stop it and adopt; only report `busy`
while another tab is actively mid-fill — and then name the tab.
Rationale: `bc._state.running` stays True after an apply session, so today's
check bricks "Fill this page" indefinitely.
Alternatives: surface a "stop first" button (rejected: an extra manual step
to work around our own stale flag).

**R4 — File tokens become mark-used-within-TTL.**
Decision: `consume_file_token` validates without popping; a token stays
redeemable for its TTL (existing TTL kept), scoped to the session.
Rationale: a transient fetch failure currently burns the token and the retry
404s into `needs_manual` — resume attach dies on first hiccup.
Alternatives: re-mint per retry (rejected: the retry happens extension-side;
the engine doesn't know to re-decide), multi-use forever (rejected: TTL
bounds exposure on the localhost port).

**R5 — Arming state survives MV3 worker death.**
Decision: persist `jobId` with the watched-tab record in
`chrome.storage.session`; `restoreWatched()` restores it so `adhoc` computes
correctly after a worker restart.
Rationale: today restore loses `jobId` → `adhoc:true` → opener (and the new
advancer) silently disarm mid-session.
Alternatives: engine re-sends `watch_start` on reconnect (already happens,
but the gap between worker revival and socket re-register still disarms).

## Fill coverage

**R6 — Label resolution ladder.**
Decision: `labelText()` (scanner.js) and the Playwright `SERIALIZE_JS`
(watcher.py) both resolve: `el.labels[0]` → `aria-label` →
`aria-labelledby` (join referenced nodes' text) → nearest ancestor `<label>`
→ preceding sibling label/heading. `automation_id` joins the engine
classifier haystack (`fields.py`).
Rationale: Workday and modern React label via `aria-labelledby`;
`div[role=combobox]` has no `.labels`; today those fields carry an empty
question and classify as unknown.
Alternatives: fuzzy nearest-text harvesting (rejected: false labels worse
than none — keep the ladder deterministic).

**R7 — Shadow DOM via a shared `deepQueryAll()`.**
Decision: one helper in scanner.js walking open shadow roots
(depth-capped), used by probe/serialize, filler's option harvest, opener,
and advancer.
Rationale: `document.querySelectorAll` never enters shadow roots — a form
inside one renders no widget at all today. Closed roots stay invisible
(accepted limitation).
Alternatives: per-module ad-hoc traversal (rejected: three implementations
to keep honest); MutationObserver per root (deferred — the 2 s poll already
covers re-scan).

**R8 — Workday widget support.**
Decision: option harvester adds `[data-automation-id=promptOption]` and
`[data-automation-id*=menuItem]`; `_WORKDAY_AUTOMATION` grows to ~20 keys
(names, contact, phone device type, source, previous-worker, country/state,
self-identification dates).
Rationale: Workday's menus match none of today's option selectors → every
dropdown is `needs_manual`; only 7 automation-ids classify.
Alternatives: full Workday adapter module (deferred to 020 if the map +
harvest prove insufficient on the manual run).

**R9 — Placeholder-value rule, shared.**
Decision: one rule in scanner.js (`jeValue`), `field_core.decide`, and
filler's `currentDisplayed`: a select whose current option's text matches
`^(select|choose|please|--|—)` (or value in `{"", "0", "-1"}` with
placeholder-ish text) counts as unanswered.
Rationale: `<option value="0">Select…</option>` reads as a chosen value →
permanently `skipped_existing`.
Alternatives: treat index-0 selection as empty always (rejected: legitimate
first options exist).

**R10 — Visibility check replaces bare `offsetParent`.**
Decision: visible = has a non-empty client rect AND computed
`visibility!=hidden` AND `display!=none`; `offsetParent===null` alone no
longer disqualifies (covers `position:fixed` fields).
Rationale: fixed-position form fields (modals) are dropped as invisible
today; `visibility:hidden` elements false-positive.
Alternatives: IntersectionObserver (rejected: async, complicates the
synchronous serialize).

**R11 — Click-guard own-name judgment for widgets.**
Decision: for ALLOW decisions on fillable widgets (combobox wrappers,
options), judge the element's own accessible name; keep descendant folding
for DENY on real buttons/submit-class controls. Mirrored in both guard
files; behavior tables updated consciously.
Rationale: a react-select wrapper whose descendant text contains "Next"
is refused today → `needs_manual` on an ordinary dropdown.
Alternatives: strip known chrome text before judging (rejected: fragile).

**R12 — Opener refresh + step-keyed one-shot.**
Decision: add modern `job-boards.greenhouse.io` Apply selectors including
links that navigate; the one-shot key becomes (doc token + control
fingerprint) instead of `location.href` — shared with the advancer.
Rationale: modern Greenhouse Apply navigates to `/application`; SPA wizards
keep the URL so href-keyed one-shot either dead-locks or double-fires.
Alternatives: keep href key with a nonce (rejected: still wrong for SPA).

## Credentials

**R13 — `form_context` produced by both serializers; `login_username` added.**
Decision: additive `Descriptor.form_context` (`"login" | "registration" |
""`): one visible password input in the form ⇒ login; two ⇒ registration
(also "create account" context text). `fields.classify` gains
`login_username` (username-labelled identifier inside a login context) and
`login_email` finally becomes reachable.
Rationale: `login_email` is dead code today — the signal it requires is
never produced and the bridge schema silently drops unknown fields.
Alternatives: engine-side inference from sibling descriptors (rejected: the
serializer sees the form; the engine sees a flat list per frame).

**R14 — Login walls become a probe state, not a hidden page.**
Decision: `probe()` stops excluding password-bearing forms; it reports
`kind:"login_wall"` (additive) so the panel renders the sign-in state
("Sign in with your saved login" / "Save a login for this site"). The
application-form heuristic itself still ignores credential fields for its
field counts (no false "3-field application" from login+search).
Rationale: the wall is where users concluded "it does nothing" — the probe's
deliberate hiding (017-era safety) is superseded by first-class handling.
Alternatives: separate hidden probe only when a vault entry exists
(rejected: the no-login case is exactly when the user needs guidance).

**R15 — Sign-in click is state-gated, one-shot per rendered document.**
Decision: the engine arms `advance_step{kind:"sign_in"}` for a frame only
when BOTH credential fills it issued there report `filled` (or
`prefilled_ok`), and fires it at most once per doc token. A re-rendered
error page (new doc token, same wall) does NOT re-arm automatically —
missing/failed state pauses to the human with the site's error visible.
Rationale: constitution v1.2.0 requires state-gating ("never inferred from
button text alone"); looping a failed login is account-lockout behavior.
Alternatives: re-arm after user edits credentials (kept: editing via the
panel save flow re-arms explicitly).

**R16 — Chrome-prefilled credentials count as satisfied.**
Decision: new terminal outcome `prefilled_ok` for credential fields whose
value was already present; it satisfies the sign-in arming condition.
Rationale: today a Chrome-password-manager-filled password reads
`skipped_existing` and the flow dead-ends.
Alternatives: overwrite the prefill with vault values (rejected: fights the
user's own password manager; theirs is as authoritative as ours).

**R17 — `credential_save` inbound message; vault-only persistence.**
Decision: additive inbound `credential_save {domain, email, password}` →
`engine/credentials.py.save()`; handler and message-layer logging redact the
payload; panel gets a minimal save form in the sign-in state.
Rationale: today a missing credential is a silent skip; Settings-only entry
forces the app round-trip 019 exists to remove.
Alternatives: deep-link to Settings only (kept as secondary path).

**R18 — Registration assist generates, fills, saves; the human clicks.**
Decision: `credentials.generate_password()` (length 20, upper/lower/digit/
symbol, no ambiguous chars); fill password + confirmation; save to vault at
fill time (idempotent overwrite); needs-you prompt "Press Create account,
then check your email." Create-account controls are final-class.
Rationale: user decision D3; verification emails and CAPTCHAs need the
human anyway, and constitution v1.2.0 keeps registration clicks forbidden.
Alternatives: save only after the site confirms the account (rejected: the
engine cannot reliably observe success; a saved-but-unused credential is
recoverable, a used-but-unsaved one is lost).

## Escort

**R19 — Completeness predicate lives in the engine.**
Decision: `escort.py` decides advance-readiness: every visible required
field terminally decided + `_inflight` empty + needs-you == 0 + no focused
field + ~2 s quiet (no new descriptors). The extension never self-decides.
Rationale: Principle IV — policy in engine; the extension is hands.
Alternatives: extension-side heuristic (rejected: splits policy, untestable
without a browser).

**R20 — `advancer.js` is the only new click site, on the opener template.**
Decision: new module with its own allowlist (`ADVANCE_ALLOWLIST` in
adapters.py, parity-tested), its own single guarded click pin, one-shot per
(doc token + fieldset hash), handling `advance_step {kind: open_apply |
sign_in | next}` → `advance_result {status, selector_kind, control_hash}`.
`filler.js` is untouched — its one-click asset pin stays green.
Rationale: the 016 opener proved this shape: allowlisted, one-shot,
parity-tested, separately pinned.
Alternatives: extend opener.js (rejected: opener is "reveal-only" by
contract; conflating weakens both pins), extend filler.js (rejected:
breaks the strongest safety test in the suite).

**R21 — Final-class deny layer beside DENY_TERMS.**
Decision: `FINAL_TERMS` in both click-guard files: submit application /
review and submit / submit / create account / register / sign up / pay /
checkout, plus `type=submit` at a terminal step; any final-class match
refuses regardless of allowlist. DENY_TERMS keeps protecting the fill path
unchanged.
Rationale: progression buttons are often literally `type=submit` inside
step forms — the old single denylist cannot express "advance yes, final
no"; two layers can.
Alternatives: rewrite DENY_TERMS semantics (rejected: fill-path behavior
must not change; parity tests pin it).

**R22 — Advance attribution windows.**
Decision: the engine records a short window around each issued
`advance_step`; `submit_detected` events inside it are attributed to the
app and excluded from `_pending_submissions` (did-you-apply tracking).
Rationale: wizard steps often POST a form; without attribution every
escorted step looks like a user submission.
Alternatives: suppress submit events extension-side during advance
(rejected: loses the audit record).

**R23 — CAPTCHA detection pauses; never interacts.**
Decision: scanner reports `captcha_present` on recaptcha/hcaptcha/turnstile
iframe/widget signatures; escort state `your_turn_captcha`; advancing past
it is blocked at the predicate level, resuming only when the signal clears
and the page progresses.
Rationale: constitution (all versions): never bypass bot protection.
Alternatives: none considered — this is a constitutional invariant.

**R24 — LinkedIn is a domain-level refusal in the advancer.**
Decision: advancer refuses all kinds on `linkedin.com` (and the engine
never arms there); filling remains available.
Rationale: user decision D4; LinkedIn actively restricts automated
accounts — the risk lands on the user's account, not ours.
Alternatives: allow with warnings (rejected: asymmetric downside).

**R25 — Escort toggle + Playwright path unchanged.**
Decision: a standing setting (default on) plus a per-session pause on the
panel; with it off, behavior is exactly today's fill-only. The Playwright
fallback path keeps user-driven advance entirely (its "advance is
user-driven" test is reworded to scope it to that path).
Rationale: cheap rollback lever for a behavior change this large;
Playwright-path escort would double the click-surface for a fallback mode.
Alternatives: escort both paths (deferred to 020).
