# Contract: bridge protocol additions (R5/R8) — PROTOCOL_V stays 1

The 010 bridge protocol (`contracts/bridge-protocol.md` in specs/010) is
unchanged except for one ADDITIVE optional field. Old companions remain valid;
no close-code semantics change.

## `hello` (extension → app) — additive field

```jsonc
{ "v": 1, "type": "hello", "seq": 1,
  "secret": "<bridge secret>",
  "version": "<manifest version — now tracks the app version via stamping>",
  "chrome_version": "138",
  "browser": "chrome"   // NEW, OPTIONAL: "chrome" | "edge" | "" (unknown)
}
```

Detection in the extension: user agent contains `Edg/` → `"edge"`, else
`"chrome"` (Chromium family). The app stores it in the companion session and
reports it via `/api/companion/doctor` and the autofill status (`extension.
browser`). Absent/empty → treated as unknown (`""`), never an error.

## Close codes (UNCHANGED semantics, NEW observability)

| Code | Meaning | New behavior on the app side | New behavior in the extension |
|---|---|---|---|
| 4401 | bad/missing secret or malformed hello | `ext_backend.record_reject("auth")` | `lastAttempt = closed:4401` → popup: "the app rejected the pairing — restart the app, then Retry; if it persists, re-load the folder shown in the app" |
| 4409 | superseded by newer session | unchanged | unchanged (silent — a newer worker owns the link) |
| 4426 | protocol version mismatch | `ext_backend.record_reject("protocol")` | `lastAttempt = closed:4426` → popup: "companion is older than the app — reload the extension (↻)" |

## Extension-side state contract (`chrome.storage.session`)

`lastAttempt {stage, port, code, at}` written by `socket.js` on EVERY
transition: `no-pairing` (pairing.json unreadable), `identity-failed`
(`/api/bridge/info` probe failed), `ws-error`, `closed` (with code),
`connected`. The popup's `status?` response includes it; a new `connect!`
runtime message triggers an immediate reconnect attempt. The popup's
"Fill this page" control, when not connected, renders the mapped reason
inline instead of doing nothing.

## Invariants preserved

- Secret never logged, never in `chrome.storage` (session storage holds NO
  secret — only stage/port/code/time), never in doctor output.
- 1 MB inbound bound, strict validation, unknown types rejected — unchanged.
- Discovery and fill message flows — unchanged.
