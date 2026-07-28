# Contract: HTTP API Additions & Changes (016)

All changes are additive or narrowing; no route is removed. Secrets never
appear in any payload (standing rule).

## `/api/autofill/status` (and the status partial's context)

- `current.pending` (blocking single question) is REMOVED.
- NEW `current.activity`: list of
  `{question, state: "drafting"|"drafted"|"filled"|"needs_you",
    answer_preview, bank_id?}` — passive log, newest first, capped 50.
- `queue.backend` unchanged (015).

## `/api/autofill/answers/confirm` and `/api/autofill/drafts/{id}/confirm`

- Behavior narrows to BANK CURATION ONLY: save/update the answer bank
  (sentinel-id guard from 015 retained). They no longer resume, unlock,
  or fill anything (`resolve_pending` retired).
- Response shape unchanged (200 + bank id) so existing UI JS keeps
  working.

## `/api/autofill/queue` (POST)

- With a live companion (`ext_backend.is_live()`), Playwright
  `preflight()` is SKIPPED (no headless launch, no 409 from it).
  Assistant-window queues keep today's preflight.

## `/api/autofill/rescan` (existing action)

- In companion mode now sends the `rescan` bridge message (was a no-op);
  response gains `{"nudged": true|false}`.

## `/api/companion/doctor`

- Additive counters: `"dropped_fields": int`, `"scan_errors": int`.
- Everything else unchanged; the pairing secret continues to NEVER be
  rendered.

## `/api/jobs/{id}/tailor` (POST)

- Same route/verb. Adds bounded execution (single local attempt,
  `timeout_s≈300`, capped prompt/output per R13).
- Failure returns 502 with `{"error": "<human-readable reason>"}` and the
  job page renders it as a visible failure state (no silent dead spinner).
- Success unchanged (persists tailoring; page reload shows it).

## Templates (server-rendered, contract-relevant)

- `partials/autofill_status.html`: review box replaced by the activity
  log; drafting entries visible (FR-019); fill-path disclosure (015 D2)
  unchanged.
- `job_detail.html`: tailor button shows an in-progress state with "can
  take a few minutes" and renders the 502 reason on failure.
