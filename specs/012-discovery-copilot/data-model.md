# Phase 1 Data Model: The Discovery Copilot

No database schema change. Discovery introduces transient message shapes over the
bridge and reuses the existing `jobs`/`companies` tables for Save.

## Transient entities (bridge messages)

### DetectedPosting → `ScoreRequest` (content → app, inbound)

The job currently on screen, read from the page. Transient; exists only to be
scored.

| Field | Type | Notes |
|-------|------|-------|
| `tab_id` | int | stamped by `relayFromContent`; routes the reply back |
| `url` | str | the posting URL (also the Save dedup key) |
| `title` | str | role title |
| `company` | str | employer name (may be "" for confidential postings) |
| `description` | str | job description text; **truncated in the handler** before scoring/logging |

Validation: strict pydantic (`extra="ignore"`), 1 MB envelope bound (existing
`parse_inbound`). Empty `title` **and** empty `description` → no meaningful score;
handler returns a neutral "not enough to score" result rather than erroring.

### DiscoveryResult → `score_result` (app → content, outbound)

The app's scored answer for a DetectedPosting.

| Field | Type | Notes |
|-------|------|-------|
| `tab_id` | int | routing (top frame) |
| `match_score` | number \| null | 0–100 from `basic_match`; null when no resume |
| `band` | str | derived from `match_score` with fixed cutoffs: **"strong" ≥ 80** (aligns with the dashboard's `high` chip), **"good" ≥ 60**, **"fair" < 60**; **"none"** when `needs_resume` (no score). These cutoffs are the single source of truth for the badge color. |
| `matching_skills` | list[str] | for the badge tooltip/detail (bounded) |
| `missing_skills` | list[str] | bounded |
| `sponsor_grade` | str \| null | "A"–"F", or null = unknown |
| `cap_exempt` | bool | university/nonprofit-research likelihood |
| `approvals` | int | H-1B approvals count when known, else 0 |
| `has_sponsor_data` | bool | false → render "H-1B: unknown" |
| `needs_resume` | bool | true → badge shows "add your resume" prompt |
| `already_saved` | bool | true → Save button shows "Already saved" |

### SaveRequest → `save_job` (content → app, inbound)

| Field | Type | Notes |
|-------|------|-------|
| `tab_id` | int | routing |
| `url` | str | dedup key |
| `title` | str | required for a valid job row |
| `company` | str | employer |
| `description` | str | truncated in handler |
| `location` | str = "" | optional; often absent at discovery time |

### SaveResult → `save_result` (app → content, outbound)

| Field | Type | Notes |
|-------|------|-------|
| `tab_id` | int | routing |
| `status` | str | "inserted" \| "updated" \| "skipped" (from `upsert_job`) |
| `job_id` | int \| null | the saved job's id when resolvable |
| `already` | bool | true when the posting already existed in the feed |

## Persisted entity (reused, no change)

### Saved Job (`jobs` row, `source="manual"`)

Save calls `db.upsert_job({url, title, company, description, source:"manual"})`
then, on success, `db.set_status(job_id, "saved")`. Reuses:

- **Dedup**: `upsert_job` — by `url` (UNIQUE), then `(company,title,location)`
  dedup_key; a repeat save returns "updated"/"skipped", never a duplicate row.
- **Feed/tracker visibility**: a `manual` job is an ordinary tracked job; status
  `saved` places it in the Saved view (`DEFAULT_FEED_STATUSES = ("none","saved")`).
- **Company creation**: `upsert_job` creates/looks up the company; the company's
  own sponsorship grade is computed by the normal pipeline as usual.

New read helper: `db.get_job_by_url(url) -> dict | None` (indexed on the existing
`jobs.url UNIQUE`) — powers `already_saved` on score, and resolves `job_id`/`already`
on save.

## State & lifecycle

- A DetectedPosting is re-derived on load and on in-place navigation (SPA); each
  triggers one `score_request` (debounced). The badge holds the latest
  DiscoveryResult for the current URL only.
- Nothing about discovery touches `ext_backend._watch`, `_inflight`, `_frame_seen`,
  or `bc._state` — the fill session's state is untouched (independence invariant).
- Dismiss is per-URL and lives in the content script's memory (no persistence).
