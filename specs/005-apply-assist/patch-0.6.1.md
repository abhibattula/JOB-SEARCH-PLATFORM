# Patch 0.6.1: Fix mac-CI test failure — millisecond timestamp collision

**Found**: 2026-07-21 — the v0.6.0 release workflow failed only in the
mac-dmg job at `python -m pytest -q`:
`tests/test_db.py::TestRefreshRuns::test_is_new_flags_jobs_from_latest_run`
— `assert by_url["old"]["is_new"] is False` got `True`. Windows and Ubuntu
were green on the identical commit, so only the Windows installer shipped
for v0.6.0.

## Root cause

`engine/db.py::_utcnow()` truncated timestamps to **milliseconds**
(`now.microsecond // 1000`). The test inserts a job, then starts a refresh
run; `is_new` is computed as `first_seen >= started_at` (inclusive). On
the fast Apple-Silicon runner, `upsert_job()` and `start_run()` executed
within the same millisecond, so the pre-run job's `first_seen` compared
equal to the run's `started_at` and the job was flagged new. A latent
flake present since feature 001 — not a 006 regression; it simply
surfaced first on the fastest runner. `engine/autofill/answer_bank.py`
duplicated the same millisecond-truncating helper (updated_at ordering —
same collision class).

## Fix

Both `_utcnow()` helpers now store full microsecond precision
(`f"{now.microsecond:06d}"`), shrinking the collision window ~1000× below
the SQLite I/O latency that always separates sequential calls. Backward
compatible by construction: `_parse_ts()`/`fromisoformat` accept both
fractional widths, SQLite's date functions accept variable fractional
digits, and lexicographic ordering of mixed-width rows remains correct.

## Verification

TDD: `tests/test_db.py::TestRefreshRuns::test_utcnow_has_microsecond_resolution`
and `tests/test_answer_bank.py::TestTimestamps::test_utcnow_has_microsecond_resolution`
written first, both confirmed failing against the old code
(`assert 3 == 6`), then green after the fix. Full suite: 302 passed.

## Ship

Version 0.6.1, tagged; both CI installers must go green (this patch
completes the half-shipped v0.6.0, whose Windows installer built but
whose mac DMG was blocked by this failure).
