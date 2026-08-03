# Contract — Panel theme delivery

**Direction**: app → extension.
**PROTOCOL_V**: **stays 1.** This is an additive field, not a version change.

## Why this is safe

`ext_protocol.outbound(type_, **payload)` (`ext_protocol.py:362-368`) builds
`{"v": PROTOCOL_V, "type": type_, "seq": seq, **payload}`. Outbound messages are
plain dicts with **no pydantic model**, so adding a key changes no schema. The
content script reads named fields off the message object; a companion that
predates this change never looks for `theme` and is unaffected (FR-036).

## The field

| Key | Type | Values | Meaning |
|---|---|---|---|
| `theme` | string | `"light"`, `"dark"`, `""` | `""` = the applicant has expressed no preference |

Source: `settings.get("THEME")`, normalised exactly as `web/main.py:112-119`
already does — any value that is not `"light"` or `"dark"` becomes `""`.

## Carriers

Added to two messages that already exist and are already handled:

| Message | Sent at | Handled at |
|---|---|---|
| `watch_start` | `ext_backend.py:75, 275, 575, 589` | `main.js` `case "watch"` |
| `overlay_state` | `ext_backend.py:403, 479, 494, 510` | `main.js:240` `case "overlay_state"` |

`watch_start` covers the panel's first paint; `overlay_state` keeps it current if
the applicant changes theme mid-session.

## Resolution order in the panel

1. `theme` field is `"light"` or `"dark"` → use it.
2. `theme` is `""`, or no message carrying it has arrived yet →
   `window.matchMedia("(prefers-color-scheme: dark)")`.
3. That API unavailable → light.

## What must not change

- Every position offset stays `!important`. This is the v1.0.0–v1.7.0 bug
  documented at `panel.js:156`; the 021 drag work depends on it (FR-037).
- Drag, position persistence in `chrome.storage.local`, and viewport clamping
  behave exactly as they do today.
- The shadow root keeps `all:initial`. Tokens are **injected**, never inherited.
- No secret, credential or pairing value is added to any message (FR-046).

## Test assertions

| # | Assertion |
|---|---|
| P1 | `PROTOCOL_V` is unchanged |
| P2 | `theme` appears on `watch_start` and `overlay_state`, and nowhere that carries a secret |
| P3 | A message without `theme` leaves the panel on the OS preference |
| P4 | `"light"` and `"dark"` each drive the corresponding panel rendering |
| P5 | The panel's token names match the app's exactly |
| P6 | Drag, persistence and clamping tests from 021 still pass unchanged |
