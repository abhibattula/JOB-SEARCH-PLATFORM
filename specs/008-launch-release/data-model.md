# Data Model — Feature 008 (Launch Release)

All schema changes are additive `_MIGRATIONS` entries in `engine/db.py`
(idempotent `ALTER TABLE … ADD COLUMN` / `CREATE TABLE IF NOT EXISTS`),
preceded by a one-time DB backup (research §9).

## Changed: `jobs`

| Column | Type | Notes |
|---|---|---|
| `last_seen_at` | TEXT | ISO µs UTC; stamped on every upsert (insert + URL-match update + dedup-key hit). Backfilled to `first_seen` on migration. |
| `delisted` | INTEGER DEFAULT 0 | 1 when a successful full-board fetch omits the job, or a HEAD check says dead. Excluded from default views; badge in `all`; saved/applied rows keep history + badge. Cleared if the job reappears. |
| `embedding` | BLOB NULL | float32 vector from EmbeddingGemma-300M, computed at ingest; NULL tolerated (rank falls back to keyword overlap). |

Display rule (no column): `posted_date IS NULL` ⇒ UI shows "seen
{first_seen}" marked approximate — never presented as the posted date.

Dedup change (behavior, not schema): dedup_key match now suppresses
duplicates **regardless of source**; on same-source repost (new URL, same
key) the existing row's URL/posted_date/last_seen_at refresh instead of
inserting a new row.

## New: `watchlist`

| Column | Type | Notes |
|---|---|---|
| `id` | INTEGER PK | |
| `ats` | TEXT | `greenhouse` \| `lever` \| `ashby` \| `workable` \| `smartrecruiters` \| `workday` |
| `slug` | TEXT | board identifier; UNIQUE(ats, slug) |
| `name` | TEXT | display name |
| `enabled` | INTEGER DEFAULT 1 | user-toggleable |
| `origin` | TEXT | `shipped` \| `user` |
| `added_at` | TEXT | ISO µs UTC |
| `last_ok_at` | TEXT NULL | last successful fetch; "board not found" surfaces in the refresh strip when NULL/stale |

Seeded once from the expanded `companies.yml` (≥300 entries) on first run
after migration; thereafter the DB is the single runtime source
(`pipeline.load_companies` reads watchlist, not YAML). User rows survive
updates (Constitution/FR-015); re-seeding only inserts unknown
`shipped`-origin slugs, never touches `user` rows or `enabled` flags.

## Changed: `user_profile`

| Column | Type | Notes |
|---|---|---|
| `search_terms` | TEXT (JSON) | `{"terms": [..≤8], "derived_from": "resume"\|"user", "updated_at": iso}` — derived by `engine/search_terms.py`, user-editable, drives jobspy. Empty ⇒ built-in defaults. |
| `resume_embedding` | BLOB NULL | resume vector, recomputed on resume upload / sections edit. |

Contact auto-fill uses **existing** identity columns (first_name,
last_name, email, phone, linkedin_url, portfolio_url, target_locations) —
no new columns; fill-only-blank; conflicts returned to the UI as
`identity_conflicts` for keep-or-replace consent (mirrors
`extraction_conflict`). Visa/work-auth columns are never written by
extraction.

## Extended pydantic: `ResumeSections` (engine/resume_extract.py)

```
contact: Contact | None      # first_name, last_name, email, phone,
                             # linkedin_url, portfolio_url, location — all optional
target_titles: list[str]     # ≤5, e.g. "Design Verification Engineer"
```

Regex fallback (basic tier): email / phone / URL patterns over the first
~15 lines of resume_text → Contact with None for anything not found.

## Settings (KV) — new/changed keys

| Key | Default | Purpose |
|---|---|---|
| `FEED_WINDOW_DEFAULT` | `14d` | new default window (constitution v1.1.1) |
| `JOBSPY_SITES` | `indeed,google` | LinkedIn appended when opt-in enabled |
| `JOBSPY_RESULTS_PER_SEARCH` | `40` | exposed knob |
| `LLM_JSON_MODEL` | `openai/gpt-oss-120b` | strict-schema cloud model (extraction/scoring) |
| `LLM_MODEL` | `llama-3.3-70b-versatile` | prose model (unchanged) |
| `LLM_PROVIDER_PRESET` | `groq` | `groq` \| `gemini` \| custom (base-url presets) |
| `WHATS_NEW_SEEN_VERSION` | `""` | What's New shown once per version |
| `UPDATE_LAST_CHECK` | `""` | once-daily startup throttle |
| `MAX_SCORE_PER_RUN` | scaled | raised in step with volume knobs |
| removed: `autofill_chromium_status` | — | ignored if present; legacy browsers dir cleanup via Diagnostics |

## In-memory: Apply Assist `_state` (browser_controller)

`fell_back: set[int]` → `outcomes: dict[job_id, {"reason":
"launch_failed"|"nav_failed"|"scan_failed"|"unrecognized"|"filled"|
"manual"|"skipped", "detail": str}]`. Exposed via `queue_snapshot()`;
UI renders a distinct message per reason. Preflight result
`{ok, channel, error}` cached per session.

## Filesystem (data_dir)

| Path | Purpose |
|---|---|
| `updates/JobEngine-Setup-<ver>.exe` (+ `.sha256`) | update download; partials deleted on startup; never executed unless digest verifies |
| `backup/jobs-v<old>.db` | pre-migration backup (keep last 2) |
| `browser-profile/` | Apply Assist isolated persistent profile (replaces `browsers/apply-assist-profile`) |
| `browsers/` (legacy) | untouched; "reclaim space" cleanup in Diagnostics |
| `crash.marker` | written by excepthooks; surfaced + cleared on next launch |
