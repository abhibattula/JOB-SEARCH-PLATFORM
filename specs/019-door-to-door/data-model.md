# Data Model: Door to Door (019)

## Entities

### Saved Login (existing, feature 005 — extended use)
| Field | Type | Notes |
|---|---|---|
| domain | str | netloc, lowercased; `__default__` for the default login |
| email / username | str | identifier; the ONLY part mirrored to SQLite (`settings` keys `cred_email:{domain}` / `cred_default_email`) |
| password | secret | OS credential vault only (keyring); write-only after save |

Lifecycle: save (panel `credential_save` or Settings) → read at fill time
(frame-domain gated) → overwrite on re-save / registration re-fill → delete
via Settings. Never exported, listed as identifiers only.

New engine API: `credentials.generate_password() -> str` (20 chars,
upper/lower/digit/symbol, no ambiguous glyphs).

### Step (new, in-memory)
The unit of one-shot advancing and completeness evaluation.
| Field | Type | Notes |
|---|---|---|
| doc | str | `data-je-doc` document token (existing) |
| fieldset_hash | str | stable hash of the step's scanned (je_idx, tag) set |
| advanced | bool | one automated advance max per Step |

### Progression Click Record (new, session activity trail)
| Field | Type | Notes |
|---|---|---|
| kind | enum | `open_apply` \| `sign_in` \| `next` |
| target | str | control description (accessible name + selector kind); never a secret |
| step | (doc, fieldset_hash) | the Step it acted on |
| outcome | enum | `clicked` \| `not_found` \| `refused` |
| at | timestamp | |

Appended to the per-job fill report; visible in the Apply Assist record.

### Escort Session State (new, additive strings on overlay_state.summary)
`escorting` · `needs_login` · `your_turn_captcha` · `ready_for_review` ·
`paused_cap` · plus existing `filling/done/stopped`.

Transitions (engine-owned, `escort.py`):
```
filling ──wall detected──────────▶ needs_login ──sign_in clicked──▶ filling
filling ──captcha_present────────▶ your_turn_captcha ──cleared────▶ filling
filling ──step complete──────────▶ (advance_step issued) ─────────▶ filling
filling ──needs_you > 0──────────▶ (paused; panel expands) ──ans──▶ filling
filling ──only final-class left──▶ ready_for_review   (terminal until human)
filling ──advance #12────────────▶ paused_cap         (terminal until human)
```
A focused user field blocks the `step complete` transition (typing wins).

### Advance-Attribution Window (new, in-memory)
| Field | Type | Notes |
|---|---|---|
| tab_id, frame_id | int | where the advance was issued |
| issued_at | monotonic | window opens |
| ttl | float | ~3 s; `submit_detected` inside → attributed to app, excluded from `_pending_submissions` |

## Protocol additions (ALL additive — PROTOCOL_V stays 1)

| Message / field | Direction | Shape |
|---|---|---|
| `Descriptor.form_context` | ext/watcher → engine | `"login" \| "registration" \| ""` (default `""`) |
| probe result additions | ext → engine | `kind:"login_wall"`, `captcha_present: bool` |
| `credential_save` | ext → engine | `{tab_id, domain, email, password}` — payload redacted from all logging |
| `advance_step` | engine → ext | `{tab_id, frame_id, kind}` |
| `advance_result` | ext → engine | `{tab_id, frame_id, kind, status, selector_kind, control_hash}` |
| `overlay_state.summary.session` | engine → ext | gains the new state strings above |
| ledger outcome | engine-internal | `prefilled_ok` (terminal, satisfies sign-in arming) |
| needs-you reasons | engine → panel | `no_saved_login`, `version_mismatch` |

Compatibility rule (tested per addition): a v1.8 companion sending v1.8
messages still validates (`_Strict extra="ignore"`); a v1.8 companion
receiving v1.9 outbound messages ignores unknown types by design; the
mismatch state (FR-001/002) is the user-visible signal, never a silent drop.

## Engine module: `escort.py` (new, pure logic)

Inputs (all existing state): scanned descriptors (visible, required,
focused), ledger outcomes per (doc, je_idx), `_inflight` size, needs-you
count, quiet-period clock, advance count per job, captcha flag, form
context, LinkedIn-domain flag, escort setting.

Outputs: `should_advance(step) -> AdvanceDecision(kind | None, reason)`,
session state string, attribution verdict for a `submit_detected`.

Constraints: no I/O, no imports from web/, fully table-testable
(`tests/test_escort.py`).

## Storage deltas

- SQLite: NONE for secrets (unchanged invariant). New `settings` rows:
  `escort_enabled` (default `"1"`). Doctor counters gain
  `version_mismatch_fills`.
- `chrome.storage.session`: watched-tab records gain `jobId` (arming
  survival, R5). Never credentials.
- OS vault: unchanged schema; registration writes use the existing
  `save(domain, email, password)`.
