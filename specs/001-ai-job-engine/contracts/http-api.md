# HTTP Contract: Personalized AI Job Engine

FastAPI app. Two route groups: **pages** (server-rendered HTML for humans) and
**JSON API** under `/api` (used by HTMX partials today; the reuse surface for any
future client). Single-user: no auth in v1; adding auth later wraps these routes
without changing shapes.

## Pages (HTML)

| Method | Path | Description |
|---|---|---|
| GET | `/` | Feed page. Renders instantly from DB (default: last 7 days, `status IN (none,saved)`, entry-level only). Embeds auto-refresh trigger. Query params: `window=7d\|24h` (default `7d`), `status=none\|saved\|applied\|hidden`, `location=<substring>`, `remote=1`, `sort=score\|date` |
| GET | `/jobs/{id}` | Job detail: description alongside match analysis, gap actions, sponsorship evidence, status buttons |
| GET | `/profile` | Resume upload + preferences form |
| GET | `/partials/feed` | HTMX partial: feed table only, same query params as `/`. Polled every 5s while a refresh is active |

## JSON API

### POST `/api/refresh`

Start a background refresh.

- Behavior: no-op (200, `{"started": false, "reason": "cooldown"|"running"}`)
  if a refresh is active or one finished < 30 min ago; otherwise starts and
  returns `{"started": true, "run_id": <int>}`. `?force=1` bypasses the cooldown
  (manual button), never the single-flight lock.

### GET `/api/refresh/status`

```json
{
  "active": true,
  "run_id": 12,
  "started_at": "2026-07-18T09:30:00",
  "sources": {
    "greenhouse": {"state": "done", "found": 120, "added": 8},
    "workday":    {"state": "running", "found": 0, "added": 0},
    "jobspy":     {"state": "queued"},
    "hn":         {"state": "failed", "error": "timeout"}
  }
}
```

`active: false` + latest run summary when idle. Source states:
`queued | running | done | failed`.

### GET `/api/jobs`

Same filters as the feed page, JSON out.

- Params: `window=7d|24h` (default `7d`), `status` (default `none,saved`),
  `location`, `remote=1`, `entry_level=1` (default), `sort=score|date`,
  `limit` (default 100), `offset`.
- Response: `{"jobs": [JobSummary], "total": <int>}` where `JobSummary` =
  `{id, title, company, location, is_remote, url, posted_date, first_seen,
  source, sponsorship, match_score, status, is_new}` (`is_new`: first seen in
  the currently active/most recent run).

### GET `/api/jobs/{id}`

Full job: `JobSummary` + `description`, `sponsorship_evidence`,
`match` (parsed `match_json`: `{match_score, matching_skills[],
missing_skills[], gap_actions[{action, impact}], reasoning}`).

### POST `/api/jobs/{id}/status`

Body: `{"status": "none"|"saved"|"applied"|"hidden"}`. Returns updated
`JobSummary`. 400 on unknown status; 404 on unknown job.

### GET `/api/profile` / POST `/api/profile`

- GET: `{resume_filename, skills[], target_locations[], preferences{},
  updated_at}` (200 with nulls when no resume yet).
- POST: multipart — optional `resume` (PDF file), optional JSON fields
  `target_locations`, `preferences`. Uploading a resume re-extracts text and
  skills. 422 if PDF has no extractable text (scanned image).

### GET `/api/export`

CSV of the current filtered feed (same params as `/api/jobs`). Polish-phase
feature.

## Error shape

All API errors: `{"detail": "<human-readable message>"}` with appropriate 4xx/5xx.
Source failures never surface as HTTP errors — they appear in refresh status.

## Contract tests

`tests/test_api.py` (FastAPI TestClient, temp DB): status codes and response
shapes for each endpoint; cooldown/single-flight behavior of `/api/refresh`;
status transition round-trip; profile upload with a fixture PDF.
