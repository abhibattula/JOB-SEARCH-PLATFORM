# Contract: App ↔ Companion Bridge (WebSocket)

Endpoint: `ws://127.0.0.1:<port>/ws/ext` (port from pairing.json).
Envelope: `{"v": 1, "type": "<name>", "seq": <int>, ...payload}`.
Pydantic schemas in `engine/autofill/ext_protocol.py` are the source of
truth; messages failing validation are dropped and counted (never crash
the session). Oversized messages (>1 MB) are rejected.

## Handshake

| Direction | Type | Payload | Semantics |
|---|---|---|---|
| ext→app | `hello` | `{secret, version, chrome_version}` | first frame, ≤5s after connect. Wrong secret → close **4401**. Version major mismatch → close **4426** (app tells user to reload extension). A newer hello supersedes an existing session → old socket closed **4409**. |
| app→ext | `hello_ok` | `{session, app_version}` | session accepted; badge → connected |

## Keepalive

`ping`/`pong` every 20s both directions tolerated; missing 2 intervals →
either side treats the link as down (app: extension.connected=false;
ext: badge gray + reconnect backoff 1s→30s + chrome.alarms watchdog).

## Commands (app → ext)

| Type | Payload | Semantics |
|---|---|---|
| `open_tab` | `{req_id, job_id, url}` | open/activate a tab; reply `tab_opened` |
| `close_tab` | `{tab_id}` | close if still open (queue advance/stop) |
| `watch_start` | `{tab_id, job_id?}` | begin scanning all frames of tab; job_id absent = ad-hoc session |
| `watch_stop` | `{tab_id}` | stop observers, remove overlay |
| `fill` | `{tab_id, frame_id, items: [FillItem]}` | apply fills in order; reply `fill_result` |
| `overlay_state` | `{tab_id, summary: {seen, filled, drafts, message}}` | update the progress panel (app-computed truth) |

`FillItem = {je_idx, kind: "text"|"select"|"checkbox"|"file"|"secret",
value?, option_label?, file_url?, flag?: "ai_draft"}`
- `secret`: fill-and-forget — never stored/logged/echoed; only sent for
  watched tabs whose frame registrable-domain matches the credential.
- `file`: `file_url` is a one-time token URL (see http-api contract).
- `flag: "ai_draft"`: filler adds the visual draft marker for that field
  in the overlay chip list.

## Events (ext → app)

| Type | Payload | Semantics |
|---|---|---|
| `tab_opened` | `{req_id, tab_id}` | correlates open_tab |
| `fields` | `{tab_id, frame_id, url, doc, descriptors: [Descriptor]}` | full per-frame scan result; sent on observer debounce (500ms), 2s safety poll, and post-fill; idempotent |
| `fill_result` | `{tab_id, frame_id, items: [{je_idx, outcome, detail?}]}` | outcomes: `filled` \| `skipped_existing` \| `focused` \| `not_found` \| `needs_manual` |
| `page_event` | `{tab_id, kind: "nav"\|"tab_closed"\|"frame_gone"\|"submit_detected", url?}` | `submit_detected` = form submit event or confirmation-page heuristic; app raises user-confirmable next-action (never auto-status) |
| `fill_here` | `{tab_id, url, title}` | user clicked "Fill this page" in popup/overlay → app starts ad-hoc session (refused with `error` if a queue job is actively filling) |

`Descriptor` is byte-identical to watcher.py SERIALIZE_JS output:
`{je_idx, doc, tag, type, name, id, label_text, placeholder, aria_label,
autocomplete, value, options?, maxlength?, focused, visible}`.

## Invariants (contract-level, tested)

1. The extension never clicks, never submits, never navigates on its own
   (open_tab/close_tab are the only tab mutations, both app-commanded).
2. The extension holds no durable state beyond last-known-good port;
   secrets and profile values never touch chrome.storage or logs.
3. All classification/value logic is app-side; the extension executes
   only explicit FillItems addressed by je_idx.
4. Every fill is re-checked just before write (empty + unfocused) —
   the user's typing always wins.
5. Scans are idempotent: re-sending the same descriptors never re-fills
   (Python ledger is authoritative).
