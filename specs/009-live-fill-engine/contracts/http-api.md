# HTTP Contract Changes — Feature 009

Routes stay thin (Constitution IV). Unlisted endpoints keep their 008
contracts.

## Apply Assist (routes_autofill)

| Route | Change |
|---|---|
| `GET /api/autofill/status` | adds `activity: {phase, fields_seen, fields_filled, message, last_scan_at, url}`; `outcomes` keeps launch/nav/scan reasons — `unrecognized` is no longer produced |
| `POST /api/autofill/queue` | unchanged shape; returns immediately (worker does the browser work) |
| `POST /api/autofill/rescan` | now "force a fill pass" → `{forced: true}`; 409 when no session |
| `POST /api/autofill/practice` | NEW — queues the bundled practice application (no job ids) → `{started: true}`; 409 when a queue is active |
| `POST /api/autofill/next` · `/stop` · `/resume-queue` · `/answers/confirm` | contracts unchanged; all browser work relocated to the worker |

## Practice pages (web/main)

| Route | Contract |
|---|---|
| `GET /practice/apply` | the bundled practice application page (HTML) |
| `GET /practice/frame` | the iframe-embedded section (HTML) |

## Profile import (routes_api)

| Route | Contract |
|---|---|
| `POST /api/profile` | SLIMMED: stores resume file/text + form fields only, then auto-starts import when a file was uploaded; performs NO AI work inline |
| `POST /api/profile/import` | start background import → `{started: true}`; 409 while running; 409 "no resume on file" |
| `GET /api/profile/import/status` | `{state: idle\|extracting\|ready\|applied\|failed, stage, chunk_done, chunk_total, error}` |
| `GET /api/profile/import/proposal` | proposal JSON (see data-model); 404 until `ready` |
| `POST /api/profile/import/apply` | `{decisions: {field: apply\|keep\|merge}}` → `{applied: [fields], profile: …}`; consumes the proposal |
| `GET /partials/profile/import` | progress banner while extracting / review screen when ready (compact confirmation when `has_differences=false`) / empty when idle |
| `POST /api/profile/reextract` | delegates to `/api/profile/import` (compat) |

## Settings

`GET/POST /api/settings` gains `prefer_local_llm` (checkbox,
default on).

## Frozen smoke additions

`/api/autofill/status` has `activity` · `/api/profile/import/status`
returns `{"state": "idle"}` · `GET /practice/apply` returns 200 HTML.
