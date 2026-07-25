# Data Model — Feature 015 (The Pairing Release)

No SQLite schema migration. New state = settings keys + small JSON files in
the data dir + in-memory/session structures. All files live under
`engine.paths.data_dir()`.

## Files

### `stamp_status.json` (NEW — written by `scripts/stamp_extension.py`)

| Field | Type | Meaning |
|---|---|---|
| `ok` | bool | pairing preparation succeeded AND read-back verified |
| `error` | string \| null | exact failure reason (exception text, or verify mismatch) |
| `at` | string (ISO 8601) | when the stamp ran |
| `port` | int \| null | port written into pairing.json |
| `app_version` | string | app version that performed the stamp |
| `copy_warning` | string \| null | non-fatal copy problem (dest already populated) |

Written on EVERY stamp attempt (success or failure — the `desktop.py` except
path writes it too). Read by `/api/companion/doctor` and the UI banners.

### `pairing.json` (existing — unchanged shape, new guarantees)

`{port, secret, app_id, protocol_v}` — now ALWAYS written even when the file
copy has problems, then read back and verified (port/secret/protocol match)
before `stamp_status.ok=true`. Freshness (mtime ≥ current process start) is a
doctor-computed property, not a stored field.

### `running.marker` (NEW — `engine/lifecycle.py`)

Empty file. Created by `mark_running()` at startup; removed by
`clear_running()` on clean shutdown. Present at startup ⇒ previous session
ended abnormally ⇒ `UNCLEAN_EXIT_AT` settings key set (ISO time) and the
one-time banner shows until dismissed (dismiss clears the key).

### `updates/cleanup.json` (NEW — `engine/updates.py`)

JSON list of absolute paths whose deletion was deferred (locked at failure
time). Drained (best-effort delete, successes removed) at the next
`startup_check`. Pruning rule (enforced after successful verify and at
startup): keep the current/in-progress artifact + at most the newest previous
`JobEngine-Setup-*.exe`; older ones deleted.

### Staged extension `manifest.json` (existing file, new write)

`stamp()` sets `"version": engine.APP_VERSION` in the STAGED copy
(`<data_dir>/extension/manifest.json`). Repo copy bumped at release.

## Settings keys (SQLite `settings` table — existing mechanism)

| Key | Values | Default | Meaning |
|---|---|---|---|
| `PREFERRED_BROWSER` | `chrome` \| `msedge` \| `auto` | `chrome` (D3) | link opening + assistant-window channel order preference |
| `UNCLEAN_EXIT_AT` | ISO string \| unset | unset | last detected abnormal end; presence drives the banner; cleared on dismiss |

## In-memory structures

### Inference request (`engine/inference.py`)

`{kind: "chat"|"embed", payload, future, submitted_at, timeout_s}` on a
bounded `queue.Queue(maxsize=32)`. Guarantees: single-flight execution (one
worker thread; in-flight counter asserts ≤1), bounded wait (timeout → clean
`RuntimeError`), bounded backlog (full queue → immediate clean failure).
Subprocess mode (R2, spike): same records forwarded over a `Pipe`; child
death fails the in-flight request cleanly and flags `runtime_restarted`.

### Companion session additions (`engine/autofill/ext_backend.py`)

- `browser: "chrome" | "edge" | ""` — from the optional `Hello.browser` field.
- Reject counters: `{auth: int, protocol: int, last_kind, last_at}` —
  incremented via `record_reject(kind)` when the web layer closes 4401/4426.
  Reset only on process restart (they describe this session's history).

### Extension-side last attempt (`chrome.storage.session`)

`lastAttempt = {stage: "no-pairing"|"identity-failed"|"ws-error"|"closed"|
"connected", port: int|null, code: int|null, at: epoch_ms}` — written by
`socket.js` on every transition; read by the popup via the `status?` message.
Session storage: survives popup churn, cleared when the browser exits.

## Derived/reported values (doctor)

`fresh` (pairing mtime ≥ process start), `port.match`
(pairing.port == int(port.txt)), `browser.mismatch`
(os_default_channel ≠ preference when preference ≠ auto), and the fill-path
disclosure string (companion+browser vs assistant+channel) — all computed at
request time, never stored.

## Invariants

1. `stamp_status.json` exists after any launch of this release (success or
   failure) — its absence itself is a red doctor finding.
2. `pairing.json.secret` is never rendered by doctor/UI/logs (existing
   fill-and-forget rule extends to diagnostics; doctor reports booleans and
   ports only).
3. Sentinel job ids (practice −1, ad-hoc −2) never reach
   `application_answers` (FR-020).
4. `PROTOCOL_V` remains 1 — `Hello.browser` is optional/additive.
