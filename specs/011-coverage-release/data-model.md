# Data Model: The Coverage Release (011)

No database changes. This release is code (guards, widget serialization,
adapters); the "entities" are in-flight message shapes and the ledger, all
in-memory and already established by 009/010.

## Changed message shapes (engine/autofill/ext_protocol.py)

### Descriptor (one serialized field) — additive fields

| Field (new) | Type | Notes |
|---|---|---|
| widget | str | `"native_select"` \| `"custom_combobox"` \| `"typeahead"` \| `""` (plain input). Drives the fill technique. |
| automation_id | str | Workday's `data-automation-id` when present, else `""`. Adapter key. |

Existing `options` now also carries a custom widget's readable option labels
(where the DOM exposes them); `value` carries the widget's currently
displayed value so "non-empty is sacred" still applies to custom widgets.

> Naming note: `Descriptor.widget` describes what a field IS
> (`custom_combobox`), while `FillItem.kind` describes the technique to
> OPERATE it (`combobox`). They are deliberately distinct — classification
> vs action — not a duplication.

### FillItem (one app→backend instruction) — new kinds

| kind | Meaning |
|---|---|
| `text` / `select` / `checkbox` / `file` / `secret` | unchanged |
| `combobox` | operate a custom dropdown: open, pick `option_label`, verify |
| `typeahead` | type `value`, then pick the matching suggestion |

`option_label` (already present for `select`) is reused for `combobox`.

## click-guard verdict (engine/autofill/click_guard.py)

Not persisted — a pure function. `is_denylisted(text, type, role) -> bool`
over `SUBMIT_DENY_PATTERNS`. The executor passes the clicked element's own
normalized text/type/role plus the concatenated text/role of its
descendants; a true verdict aborts the click and yields outcome
`needs_manual`.

## Fill outcome vocabulary (unchanged)

`filled` · `skipped_existing` (kept your value) · `no_match` · `needs_manual`
· `focused` — now also produced for `combobox`/`typeahead`. Terminal set in
`field_core.TERMINAL_OUTCOMES` unchanged. A `combobox`/`typeahead` fill that
succeeds records `filled`; a wrong/absent option records `no_match`; a
timed-out or un-openable widget records `needs_manual`.

## Handled ledger (unchanged)

`(doc_token, je_idx) → terminal outcome`, per job, in `browser_controller.
_state.handled`. Custom widgets settle by the same keys — a filled combobox
is not re-touched; a `needs_manual` widget is retried only on a genuinely new
scan (same idempotency as native fields).

## Extension-side state (unchanged, bounded)

`chrome.storage.local`: last-known-good port only. DOM: `data-je-idx` stamps
+ doc token. The denylist is code, not state. No secrets, no widget values
persisted.
