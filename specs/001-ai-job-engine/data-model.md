# Data Model: Personalized AI Job Engine

SQLite database at `data/jobs.db` (override via `JOBS_DB_PATH`). Schema created
idempotently by `engine/db.py` on startup; WAL mode enabled (concurrent web reads
during background refresh writes).

## Tables

### companies

| Column | Type | Constraints | Notes |
|---|---|---|---|
| id | INTEGER | PRIMARY KEY | |
| name | TEXT | UNIQUE NOT NULL | display name |
| normalized_name | TEXT | INDEX | casefolded, suffixes (Inc/LLC/Corp…) stripped — join key for sponsorship data |
| ats_type | TEXT | NULL | `greenhouse` \| `lever` \| `ashby` \| `workday` \| NULL (companies discovered via jobspy/HN have no ATS entry) |
| ats_slug | TEXT | NULL | board slug / Workday `tenant:site` |
| h1b_approvals | INTEGER | DEFAULT 0 | total approvals from USCIS Data Hub (recent FYs) |
| lca_titles | TEXT | NULL | JSON array of job titles from DOL LCA disclosures |
| sponsor_score | TEXT | DEFAULT 'UNKNOWN' | `HIGH` \| `MEDIUM` \| `UNKNOWN` (per-company; per-job rating may downgrade to EXCLUDED via JD text) |

### jobs

| Column | Type | Constraints | Notes |
|---|---|---|---|
| id | INTEGER | PRIMARY KEY | |
| company_id | INTEGER | FK → companies.id, NOT NULL | |
| title | TEXT | NOT NULL | |
| location | TEXT | NULL | raw source string |
| is_remote | BOOLEAN | DEFAULT 0 | derived from location/remote flags |
| description | TEXT | NULL | plain text (HTML stripped) |
| url | TEXT | UNIQUE NOT NULL | apply/detail link |
| dedup_key | TEXT | UNIQUE | sha1(normalized company \| title \| location) — cross-source dedup |
| source | TEXT | NOT NULL | `greenhouse` \| `lever` \| `ashby` \| `workday` \| `hn` \| `jobspy` |
| posted_date | TEXT (ISO date) | NULL | source-provided; may be absent |
| first_seen | TEXT (ISO datetime) | NOT NULL DEFAULT now | set on insert, never updated |
| is_entry_level | BOOLEAN | NULL | NULL = not yet classified |
| sponsorship | TEXT | DEFAULT 'UNKNOWN' | per-job rating: `HIGH` \| `MEDIUM` \| `EXCLUDED` \| `UNKNOWN` |
| sponsorship_evidence | TEXT | NULL | JSON: matched phrase, approval count used |
| match_score | REAL | NULL | 0–100; NULL = unscored |
| match_json | TEXT | NULL | full validated LLM analysis (skills, gaps, reasoning) |
| status | TEXT | DEFAULT 'none' | `none` \| `saved` \| `applied` \| `hidden` — user-set, preserved on upsert |

Indexes: `(posted_date)`, `(status)`, `(is_entry_level, sponsorship)`.

**Recency rule**: feed windows use `COALESCE(posted_date, date(first_seen))`.

**Upsert rule**: match on `url` (or `dedup_key`); update `posted_date` (if fresher)
and `description`; never overwrite `first_seen`, `status`, `match_score`,
`match_json`.

### user_profile

Single row (id = 1) in v1; structure does not preclude more rows later.

| Column | Type | Notes |
|---|---|---|
| id | INTEGER PRIMARY KEY | fixed 1 in v1 |
| resume_text | TEXT | extracted from uploaded PDF |
| resume_filename | TEXT | for display |
| skills | TEXT | JSON array (LLM-extracted on upload) |
| target_locations | TEXT | JSON array — pre-populates the location filter only (never hard-excludes) |
| preferences | TEXT | JSON object (future-proof bag: remote_only default, etc.) |
| updated_at | TEXT | ISO datetime |

### refresh_runs

| Column | Type | Notes |
|---|---|---|
| id | INTEGER PRIMARY KEY | |
| started_at | TEXT | ISO datetime |
| finished_at | TEXT | NULL while running |
| trigger | TEXT | `auto` \| `manual` \| `cli` \| `scheduled` |
| source_status | TEXT | JSON: per source `{state: queued\|running\|done\|failed, found, added, error}` |

**Cooldown rule**: auto-refresh is skipped if the latest run finished < 30 min ago
or a run has `finished_at IS NULL` (single-flight; a stale unfinished run older
than 30 min is treated as crashed and superseded).

## State transitions

### Job status (user-driven)

```
none ──save──▶ saved ──┐
none ──apply──▶ applied │  any state ──▶ any other state (one click, reversible)
none ──hide──▶ hidden ──┘
```

- Default feed: `status IN ('none','saved')`
- Saved / Applied / Hidden views: `status = X`
- Refresh upserts never modify `status`.

### Job processing lifecycle (pipeline-driven)

```
inserted (is_entry_level NULL)
   └─▶ classified (is_entry_level 0|1, sponsorship rated)
          └─▶ scored (match_score set)          [only if is_entry_level=1 and resume exists]
          └─▶ unscored (match_score NULL)       [LLM failed twice or no resume — still visible]
```

## Validation rules (from FRs)

- Every job MUST have `title`, `url`, `source`, `company_id`, `first_seen` (FR-001/002).
- `sponsorship = 'EXCLUDED'` whenever a negative phrase matched, regardless of
  `companies.sponsor_score` (FR-009).
- `match_json` MUST parse into the pydantic `MatchAnalysis` model before being
  stored (FR-012); invalid → NULL after one retry.
- Feed queries MUST exclude `applied`/`hidden` by default (FR-003/FR-017) and
  apply location narrowing only when the filter is active (FR-018).
