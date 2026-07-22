# HTTP Contracts: The Moat Release (007)

Additions/changes only; all existing endpoints keep their contracts.
Additive response fields never break existing exact-match tests (the 006
lesson: relax equality assertions when extending payloads).

## Profile / resume builder

### POST /api/profile (extended, multipart — existing route)
- New behavior: when a `resume` file is uploaded, its original bytes are
  stored and `resume_file_path` is set; structured extraction runs when an
  AI tier is available.
- New response fields: `resume_sections` (object|null),
  `extraction_conflict` (bool) — true when extraction was skipped because
  user-edited sections exist; the UI then offers keep vs re-extract.
- `resume_file_path` itself is never exposed (server-local path).

### GET /api/profile (extended)
- Adds `resume_sections` (object|null), `sections_edited_at` (string|null),
  `has_resume_file` (bool).

### PUT /api/profile/resume-sections
- Body: full `ResumeSections` JSON (schema-validated).
- Replaces stored sections, stamps `sections_edited_at`. 422 on invalid
  shape. Response: saved sections.

### POST /api/profile/reextract
- Explicit consent path after `extraction_conflict` (or the builder's
  re-extract button). Runs extraction from the stored resume text,
  replaces sections, clears `sections_edited_at`.
- 409 if no resume on file; `{"extracted": false, "reason": "no-ai-tier"}`
  when no LLM is available (manual forms remain).

## Tailored documents

### GET /api/jobs/{id}/resume-pdf
- Returns `application/pdf` (attachment) — tailored when tailoring exists,
  otherwise untailored from sections alone (FR-018/019). Re-renders on
  fingerprint mismatch. 409 when no resume sections exist at all.

### GET /api/jobs/{id}/cover-letter-pdf
- Returns `application/pdf`. 409 when the job has no tailoring output.

## Apply Assist

### GET /partials/autofill/status + GET /api/autofill/status (extended)
- Adds: `queue` (ordered list of `{job_id, title, company, state}` where
  state ∈ pending|current|done|failed), `progress` (`{done, total}`),
  `current` now includes `title` and `company`, `fill_report` (list of
  `{label, tag, value_preview, outcome}` for the current job; password
  entries are pre-masked), `interrupted` (bool — browser closed,
  resumable).

### POST /api/autofill/rescan
- Re-classifies and fills the current page (manual fallback for SPA
  re-renders). `{"rescanned": true, "filled": N}`; 409 when no active
  session.

### POST /api/autofill/resume-queue
- Relaunches the browser at the current queue position after an
  interruption. `{"resumed": true}`; 409 when nothing to resume.

### POST /api/autofill/queue (existing) — response unchanged; queue end
  now also produces a `summary` field on the status payload:
  `{filled: N, manual: N, skipped: N, per_job: [{job_id, outcome}]}`.

## Sponsorship intelligence

### GET /api/jobs (extended)
- New filter param: `strong_sponsors=1` (grade ≥ B or cap-exempt;
  composes with existing params).
- Job rows add: `sponsor_grade` (string|null), `cap_exempt` (bool).

### GET /api/jobs/{id} (extended)
- Adds `sponsor_evidence` object: `{approvals, denials, approval_rate,
  wage_level_median, wage_offered_median, lottery_hint, cap_exempt,
  grade, grade_reasons: [string]}` (nulls where data absent).

## Settings / theme / diagnostics

### POST /api/settings (extended)
- Accepts `THEME` (`light`|`dark`) and `AUTOFILL_USE_TAILORED_PDF`
  (`0`|`1`) through the existing settings save path.

### GET /api/diagnostics/pdf-selftest
- Renders a minimal PDF in-process; 200 + `{ok: true, bytes: N}` on
  success. Wired into `packaging/smoke_test.py` (real-execution check,
  v0.4.0 lesson).

## Pages (server-rendered, contract = renders without error)

- `/profile` gains the Resume builder section (extracted/manual forms,
  keep-vs-re-extract prompt when flagged).
- `/` (Applied view) gains board/table toggle; board renders stage
  columns with counts.
- `/autofill` gains the mission-control panel (queue list, progress,
  fill report, batch summary).
- All pages render correctly under both themes (`data-theme` stamped by
  base template from the setting).
