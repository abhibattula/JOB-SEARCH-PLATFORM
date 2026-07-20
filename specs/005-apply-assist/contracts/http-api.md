# HTTP Contract: Apply Assist (additive to `specs/001-ai-job-engine/contracts/http-api.md`)

New routes only. Same conventions as the existing contract: FastAPI,
single-user (no auth), pages return server-rendered HTML, `/api` returns
JSON, used by HTMX partials.

## Pages (HTML)

| Method | Path | Description |
|---|---|---|
| GET | `/autofill` | Apply Assist page: job-selection (from existing shortlist/status), queue status once running, current job's field-fill summary, pending answer-bank confirmations, "Done, next application" control, Chromium first-use install prompt/progress if not yet installed |
| GET | `/partials/autofill/status` | HTMX partial: current queue state (idle / running + current job / awaiting confirmation). Polled while a queue is active, same pattern as `/api/refresh/status`'s polling |

## JSON API

### POST `/api/autofill/setup`

One-time Chromium install for Apply Assist (spec: first-use browser-engine
download).

- Behavior: `{"started": true}` and begins `playwright install chromium` as
  a background subprocess if not already installed; `{"started": false,
  "reason": "already_installed"}` if it is. Progress is reported via the
  status partial above, not this endpoint's response.

### POST `/api/autofill/queue`

Start an Apply Assist session over a set of shortlisted jobs.

- Body: `{"job_ids": [int, ...]}`
- 409 if Chromium isn't installed yet (`/api/autofill/setup` must run
  first) or a queue is already running.
- 200 `{"started": true, "current_job_id": <int>}` on success.

### POST `/api/autofill/next`

The user's explicit "Done, next application" action (spec clarify: advance
is user-driven, never automatic completion detection).

- 200 `{"current_job_id": <int>}` if another job remains in the queue.
- 200 `{"current_job_id": null, "finished": true}` if the queue is now
  exhausted (returns to idle).

### POST `/api/autofill/stop`

Ends the current queue early (spec edge case: user closes the browser
window or wants to bail). 200 `{"stopped": true}`; idempotent if already
idle.

### GET `/api/autofill/status`

```json
{
  "chromium_installed": true,
  "queue_active": true,
  "current_job_id": 42,
  "remaining": 3,
  "pending_confirmation": {
    "question_raw": "Do you require visa sponsorship now or in the future?",
    "category": "sponsorship_requirement",
    "drafted_answer": "..."
  }
}
```

`pending_confirmation` is `null` unless the queue is currently paused
awaiting a user confirm/edit on an unrecognized or legally-sensitive
question (FR-011, FR-012) — the browser session itself pauses too; no
further fields are filled until this is resolved.

### POST `/api/autofill/answers/confirm`

Confirms (optionally edited) a drafted answer, per the review-before-use
gate (FR-011). This is the **only** write path into `answer_bank` — no other
endpoint or background process may insert/update a row there.

- Body: `{"question_raw": "...", "answer": "...", "category": "..."}`
- 200 `{"saved": true}`; the confirmed answer is then applied to the field
  that triggered the pause and recorded in `application_answers` for the
  current job (FR-021).

## Credentials (Settings page additions)

### POST `/api/credentials`

Save/update a per-domain login. Body: `{"domain": "...", "email": "...",
"password": "..."}`. 200 `{"saved": true}`. The password is never echoed
back in this or any other response (FR-017).

### GET `/api/credentials`

`{"domains": [{"domain": "...", "email": "..."}]}` — identifiers only,
never secrets (matches `engine/credentials.py::list_domains()` behavior in
data-model.md).

### DELETE `/api/credentials/{domain}`

200 `{"deleted": true}`; clears both the keychain entry and the
`cred_email:{domain}` settings row (data-model.md invariant).
