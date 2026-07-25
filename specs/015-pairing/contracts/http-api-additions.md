# Contract: HTTP API additions (R5/R6/R7)

All additions are additive; no existing field changes meaning or shape.

## GET `/api/companion/doctor` (NEW)

One snapshot of the entire pairing chain. 200 always (fields degrade to
null/false rather than erroring).

```jsonc
{
  "stamp":     { "ok": true, "error": null, "at": "2026-07-25T18:00:00Z",
                 "port": 8000, "app_version": "1.5.0", "copy_warning": null },
  "pairing":   { "present": true, "port": 8000, "protocol_v": 1, "fresh": true },
  "port":      { "current": 8000, "match": true },
  "companion": { "connected": true, "version": "1.5.0",
                 "browser": "chrome", "last_seen_age_s": 2.1 },
  "rejects":   { "auth": 0, "protocol": 0,
                 "last_kind": null, "last_age_s": null },
  "browser":   { "os_default_channel": "msedge", "preference": "chrome",
                 "mismatch": true }
}
```

Semantics: `pairing.fresh` = pairing.json mtime ≥ this process's start;
`port.match` = pairing.port == port.txt; `rejects` counts this process's
4401/4426 closes; secrets are NEVER included. Consumers: connect wizard
(3 s poll), diagnostics page, frozen smoke, E2E test.

## POST `/api/os/default-apps` (NEW, Windows only)

Opens the OS default-apps settings (`ms-settings:defaultapps`). 200
`{"opened": true}` on Windows; 409 `{"detail": "..."}` elsewhere. No body.

## GET/POST `/api/open` (EXISTING — additive change)

Now honors `PREFERRED_BROWSER` (R6). Response gains
`"opened_with": "chrome" | "msedge" | "os-default"` so the UI can note
substitutions (preferred browser missing → OS default + note).

## POST `/api/autofill/queue` (EXISTING — additive)

Response gains `"backend": "extension" | "playwright"` (the sticky choice for
this run) so the UI can show the D2 notice from the very first render.

## GET `/api/autofill/status` (EXISTING — additive)

`extension` object gains `"browser"`; consumers render the fill-path
disclosure: companion → "your <Browser> (companion v<version>)", playwright →
"assistant window — <Channel> (not signed in)" + connect link when the
companion is absent (D2/FR-012/013).

## POST `/api/autofill/answers/confirm` (EXISTING — behavior fix, R10)

For practice/ad-hoc sessions (job_id ≤ 0): still 200; the reusable answer is
saved; NO per-application snapshot row is written (previously 500 via FK).
