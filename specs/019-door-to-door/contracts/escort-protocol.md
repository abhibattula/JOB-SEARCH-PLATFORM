# Contract: Escort Bridge Protocol (019 additions)

PROTOCOL_V stays **1**. Every change below is additive; `_Strict` models keep
`extra="ignore"`. A v1.8 companion must connect, fill, and show the mismatch
state — never break, never silently lose work (guarded by
`tests/test_ext_protocol.py::TestCompat019`).

## Inbound (extension → engine)

### `credential_save`
```json
{"v": 1, "type": "credential_save", "tab_id": 12,
 "domain": "company.wd5.myworkdayjobs.com",
 "email": "user@example.com", "password": "•••"}
```
- Handler calls `credentials.save(domain, email, password)` (vault-only).
- The message payload MUST be excluded from every log/echo path; the ack
  carries `{ok: true, domain}` only — never the secret, never the email.
- Saving re-arms the sign-in flow for the reporting tab.

### `advance_result`
```json
{"v": 1, "type": "advance_result", "tab_id": 12, "frame_id": 0,
 "kind": "next", "status": "clicked",
 "selector_kind": "workday_bottom_next", "control_hash": "a1b2c3"}
```
- `kind`: `open_apply` | `sign_in` | `next` — the report channel covers ALL
  progression clicks. `open_apply` results are reported by the opener
  (which remains the sole Apply-click owner); `sign_in`/`next` by the
  advancer.
- `status`: `clicked` | `not_found` | `refused`.
- Every result (including refusals) lands in the Progression Click Record
  trail. `refused` never retries the same (doc, control_hash). A `not_found`
  on a complete step pauses the session to the human (FR-024).

### Extended: `fields` descriptors
- `Descriptor.form_context`: `"login" | "registration" | ""` (default `""`).
- Probe report gains `kind: "login_wall"` and `captcha_present: bool`.

## Outbound (engine → extension)

### `advance_step`
```json
{"v": 1, "type": "advance_step", "tab_id": 12, "frame_id": 0,
 "kind": "next", "step_key": "d4t0k3n:f13lds"}
```
- `kind`: `sign_in` | `next`. (`open_apply` is NOT an advance_step kind —
  form-opening stays owned by the opener, per constitution v1.2.0's
  "separate, allowlisted, one-shot step"; the opener reports its click via
  `advance_result` so the trail is complete.)
- `step_key` is engine-computed (doc token + fieldset hash); the advancer
  refuses a second click for a step_key it has already acted on.
- Routed to the EXACT frame (`chrome.tabs.sendMessage {frameId}`), same as
  fills. `sign_in` may only ever be issued for the frame whose credential
  fills the engine itself confirmed (`filled` / `prefilled_ok`).
- The engine issues at most one `advance_step` per Step (doc token +
  fieldset hash) and at most 12 `next` advances per job.

### Extended: `overlay_state.summary.session`
New values: `escorting`, `needs_login`, `your_turn_captcha`,
`ready_for_review`, `paused_cap`. Old companions ignore unknown values and
keep rendering `filling/done/stopped` behavior.

## Version-skew contract

- `hello_ok` already carries `app_version`; the companion MUST compare it to
  its own manifest version and persist `{appVersion, mismatch}` to
  `chrome.storage.session`.
- On mismatch: popup and panel render the reload instruction; the app's
  connect page renders amber (server-side compare of the `hello` version).
- The engine MUST NOT silently discard any fill because of skew: a withheld
  capability surfaces as `needs_manual` with reason `version_mismatch` and
  increments the doctor counter `version_mismatch_fills`.

## Secret-safety invariants (re-verified by `tests/test_secret_hygiene.py`)

A password value appears ONLY: in the vault; in the `credential_save`
payload in transit on localhost; in `fill` items of `kind:"secret"` in
transit; in the page's input element. It never appears in: SQLite,
`chrome.storage` (any area), engine logs, extension console (logSafe strips
values), fill reports (masked at record time), the answers feed
(`page_answers` excludes secrets), doctor output, or any test artifact.
