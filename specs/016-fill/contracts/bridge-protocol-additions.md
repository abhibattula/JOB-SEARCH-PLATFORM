# Contract: Bridge Protocol Additions (016)

`PROTOCOL_V` remains **1**. Every change below is additive; unknown
messages/fields are ignored by both sides (`Descriptor`/models are
`extra="ignore"`; the extension switch has a default case). Version-gated
behavior is explicit where an old peer could misbehave.

## New outbound messages (app → extension)

### `rescan`
```json
{ "type": "rescan", "reason": "draft_ready | fill_again | user_rescan" }
```
Content script response: run a scan immediately (same path as the 2 s
tick). Sent when a draft completes, when the panel's Fill again fires
(after app-side ledger/backoff reset), and from the app's Re-scan action.
Old extensions ignore it silently (no harm — the 2 s tick still runs).

## New inbound messages (extension → app)

### `child_tab`
```json
{ "type": "child_tab", "tab_id": 123, "opener_tab_id": 45 }
```
Sent from `tabs.onCreated` when `opener_tab_id` is the watched tab. App
transfers `_watch.tab_id` to `tab_id` (newest child wins) and sends
`watch_start` for it.

### `scan_error`
```json
{ "type": "scan_error", "tab_id": 123, "message": "TypeError: ..." }
```
Replaces today's swallowed content-script scan exception. App increments
the doctor `scan_errors` counter (message truncated to 200 chars; never
logged with page content).

## Extended message fields (additive)

### `Descriptor` (inside `fields`)
- `members: [{"je_idx": int, "label": str}]` (default `[]`) — radio-group
  members (see data-model §1 for grouping rules).
- `required: bool` (default `false`).
- `type` may now be `"radio_group"`.

### `FillItem` (inside `fill`)
- `kind` gains `"radio"` — `value` is the member LABEL to check.
- `flag` gains `"needs_you"` (existing `"ai_draft"` now rendered).

**Version gate (app-side)**: items with `kind:"radio"` (or any
016-introduced kind) are sent only when the companion hello `version` ==
app `APP_VERSION`. Otherwise the field is skipped and flagged `needs_you`
via a text-safe annotation fill (no new kind on the wire).

## Unchanged

`hello` (secret model untouched), `open_tab`/`tab_opened`, `watch_start`,
`fields` cadence (2 s + MutationObserver), `fill_result`, `page_event`,
close codes 4401/4409/4426 and their popup mapping (015).

## Ordering & safety invariants

- The app never sends `fill` for a tab other than the current watch
  target; wrong-tab inbound `fields` increment `dropped_fields` (doctor).
- `rescan` is fire-and-forget; at most one queued per tab at a time
  (coalesced app-side).
- No message ever contains the pairing secret or page content beyond the
  existing descriptor fields.
