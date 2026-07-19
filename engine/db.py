"""SQLite persistence: schema, upserts with dedup, feed queries, refresh runs.

All timestamps are stored as UTC strings. Connections are opened per call so the
background refresh thread and web request threads never share one. WAL mode
requires the database to live on a local disk.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterator, Mapping

COOLDOWN_MINUTES = 30
STALE_RUN_MINUTES = 30
VALID_STATUSES = {"none", "saved", "applied", "hidden"}
DEFAULT_FEED_STATUSES = ("none", "saved")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS companies (
    id INTEGER PRIMARY KEY,
    name TEXT UNIQUE NOT NULL,
    normalized_name TEXT,
    ats_type TEXT,
    ats_slug TEXT,
    h1b_approvals INTEGER DEFAULT 0,
    lca_titles TEXT,
    sponsor_score TEXT DEFAULT 'UNKNOWN',
    sponsor_checked INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_companies_norm ON companies(normalized_name);

CREATE TABLE IF NOT EXISTS jobs (
    id INTEGER PRIMARY KEY,
    company_id INTEGER NOT NULL REFERENCES companies(id),
    title TEXT NOT NULL,
    location TEXT,
    is_remote INTEGER DEFAULT 0,
    description TEXT,
    url TEXT UNIQUE NOT NULL,
    dedup_key TEXT,
    source TEXT NOT NULL,
    posted_date TEXT,
    first_seen TEXT NOT NULL,
    is_entry_level INTEGER,
    sponsorship TEXT DEFAULT 'UNKNOWN',
    sponsorship_evidence TEXT,
    match_score REAL,
    match_json TEXT,
    status TEXT DEFAULT 'none'
);
CREATE INDEX IF NOT EXISTS idx_jobs_posted ON jobs(posted_date);
CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
CREATE INDEX IF NOT EXISTS idx_jobs_entry ON jobs(is_entry_level, sponsorship);
CREATE INDEX IF NOT EXISTS idx_jobs_dedup ON jobs(dedup_key);

CREATE TABLE IF NOT EXISTS user_profile (
    id INTEGER PRIMARY KEY,
    resume_text TEXT,
    resume_filename TEXT,
    skills TEXT,
    target_locations TEXT,
    preferences TEXT,
    updated_at TEXT
);

CREATE TABLE IF NOT EXISTS refresh_runs (
    id INTEGER PRIMARY KEY,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    trigger TEXT,
    source_status TEXT DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT
);

CREATE TABLE IF NOT EXISTS h1b_employers (
    normalized_name TEXT PRIMARY KEY,
    display_name TEXT,
    approvals INTEGER DEFAULT 0,
    lca_titles TEXT
);
"""


def get_db_path() -> Path:
    override = os.environ.get("JOBS_DB_PATH")
    if override:
        return Path(override)
    from . import paths

    return paths.data_dir() / "jobs.db"


def _utcnow() -> str:
    now = datetime.now(timezone.utc)
    return now.strftime("%Y-%m-%d %H:%M:%S.") + f"{now.microsecond // 1000:03d}"


def _parse_ts(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


@contextmanager
def _conn() -> Iterator[sqlite3.Connection]:
    path = get_db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


APPLICATION_STAGES = ("applied", "oa", "interview", "offer", "rejected")
FOLLOW_UP_DAYS = 7

# columns added after the original schema; applied idempotently on startup
_MIGRATIONS = {
    "jobs": [
        ("tailor_json", "TEXT"),
        ("stage", "TEXT"),
        ("applied_at", "TEXT"),
        ("stage_updated_at", "TEXT"),
        ("notes", "TEXT"),
    ],
}


def init_db() -> None:
    with _conn() as conn:
        conn.executescript(_SCHEMA)
        for table, columns in _MIGRATIONS.items():
            existing = {
                row["name"]
                for row in conn.execute(f"PRAGMA table_info({table})").fetchall()
            }
            for column, ddl_type in columns:
                if column not in existing:
                    conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl_type}")


def normalize_company(name: str) -> str:
    cleaned = re.sub(r"[^\w\s]", " ", (name or "").casefold())
    words = cleaned.split()
    suffixes = {"inc", "incorporated", "llc", "corp", "corporation", "ltd",
                "limited", "co", "company", "plc", "lp", "llp"}
    while words and words[-1] in suffixes:
        words.pop()
    return " ".join(words)


def _dedup_key(company: str, title: str, location: str | None) -> str:
    basis = "|".join(
        re.sub(r"\s+", " ", (part or "").casefold().strip())
        for part in (normalize_company(company), title, location or "")
    )
    return hashlib.sha1(basis.encode("utf-8")).hexdigest()


def _get_or_create_company(
    conn: sqlite3.Connection,
    name: str,
    ats_type: str | None = None,
    ats_slug: str | None = None,
) -> int:
    row = conn.execute("SELECT id FROM companies WHERE name = ?", (name,)).fetchone()
    if row:
        return row["id"]
    cur = conn.execute(
        "INSERT INTO companies (name, normalized_name, ats_type, ats_slug)"
        " VALUES (?, ?, ?, ?)",
        (name, normalize_company(name), ats_type, ats_slug),
    )
    return cur.lastrowid


def upsert_job(job: Mapping[str, Any]) -> str:
    """Insert or refresh one job. Returns 'inserted' | 'updated' | 'skipped'.

    Updates never touch first_seen, status, classification, or match results.
    A job whose (company, title, location) already exists via a *different*
    source is treated as a cross-source duplicate and skipped.
    """
    url = job["url"]
    dedup = _dedup_key(job["company"], job["title"], job.get("location"))
    with _conn() as conn:
        existing = conn.execute("SELECT * FROM jobs WHERE url = ?", (url,)).fetchone()
        if existing:
            new_posted = job.get("posted_date")
            posted = existing["posted_date"]
            if new_posted and (posted is None or new_posted > posted):
                posted = new_posted
            conn.execute(
                "UPDATE jobs SET title=?, location=?, is_remote=?,"
                " description=COALESCE(NULLIF(?, ''), description), posted_date=?"
                " WHERE id=?",
                (
                    job["title"],
                    job.get("location"),
                    1 if job.get("is_remote") else 0,
                    job.get("description") or "",
                    posted,
                    existing["id"],
                ),
            )
            return "updated"
        duplicate = conn.execute(
            "SELECT id FROM jobs WHERE dedup_key = ? AND source != ?",
            (dedup, job["source"]),
        ).fetchone()
        if duplicate:
            return "skipped"
        company_id = _get_or_create_company(
            conn, job["company"], job.get("company_ats_type"), job.get("company_ats_slug")
        )
        conn.execute(
            "INSERT INTO jobs (company_id, title, location, is_remote, description,"
            " url, dedup_key, source, posted_date, first_seen)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                company_id,
                job["title"],
                job.get("location"),
                1 if job.get("is_remote") else 0,
                job.get("description") or "",
                url,
                dedup,
                job["source"],
                job.get("posted_date"),
                _utcnow(),
            ),
        )
        return "inserted"


_JOB_COLUMNS = (
    "j.id, j.title, j.location, j.is_remote, j.url, j.source, j.posted_date,"
    " j.first_seen, j.is_entry_level, j.sponsorship, j.match_score, j.status,"
    " json_extract(j.match_json, '$.method') AS match_method,"
    " j.stage, j.applied_at, j.stage_updated_at, j.notes,"
    " c.name AS company"
)


def _row_to_job(row: sqlite3.Row, latest_start: str | None) -> dict:
    job = dict(row)
    job["is_remote"] = bool(job.get("is_remote"))
    if latest_start is not None and job.get("first_seen"):
        job["is_new"] = _parse_ts(job["first_seen"]) >= _parse_ts(latest_start)
    else:
        job["is_new"] = False
    job["follow_up"] = bool(
        job.get("stage") == "applied"
        and job.get("stage_updated_at")
        and datetime.now(timezone.utc) - _parse_ts(job["stage_updated_at"])
        > timedelta(days=FOLLOW_UP_DAYS)
    )
    return job


def query_jobs(
    window: str | None = "7d",
    statuses: list[str] | tuple[str, ...] | None = DEFAULT_FEED_STATUSES,
    entry_level: bool | None = None,
    location: str | None = None,
    remote: bool | None = None,
    sort: str = "score",
    limit: int = 100,
    offset: int = 0,
    ineligible: bool = False,
    include_ineligible: bool = False,
    min_score: float | None = None,
) -> tuple[list[dict], int]:
    where, params = [], []
    # Sponsorship-ineligible (EXCLUDED) jobs never appear in normal views;
    # ineligible=True is the audit view showing only them.
    if ineligible:
        where.append("j.sponsorship = 'EXCLUDED'")
    elif not include_ineligible:
        where.append("j.sponsorship != 'EXCLUDED'")
    if window in ("7d", "24h"):
        days = 7 if window == "7d" else 1
        where.append(
            "date(COALESCE(j.posted_date, j.first_seen)) >= date('now', ?)"
        )
        params.append(f"-{days} days")
    if statuses:
        placeholders = ",".join("?" for _ in statuses)
        where.append(f"j.status IN ({placeholders})")
        params.extend(statuses)
    if entry_level is True:
        where.append("j.is_entry_level = 1")
    elif entry_level is False:
        where.append("(j.is_entry_level = 0 OR j.is_entry_level IS NULL)")
    if location:
        where.append("j.location LIKE ?")
        params.append(f"%{location}%")
    if remote:
        where.append("j.is_remote = 1")
    if min_score is not None:
        where.append("j.match_score >= ?")
        params.append(min_score)
    clause = f" WHERE {' AND '.join(where)}" if where else ""
    order = (
        " ORDER BY j.match_score IS NULL, j.match_score DESC,"
        " COALESCE(j.posted_date, j.first_seen) DESC"
        if sort == "score"
        else " ORDER BY COALESCE(j.posted_date, j.first_seen) DESC"
    )
    with _conn() as conn:
        latest = conn.execute(
            "SELECT started_at FROM refresh_runs ORDER BY id DESC LIMIT 1"
        ).fetchone()
        latest_start = latest["started_at"] if latest else None
        total = conn.execute(
            f"SELECT COUNT(*) AS n FROM jobs j JOIN companies c ON j.company_id = c.id{clause}",
            params,
        ).fetchone()["n"]
        rows = conn.execute(
            f"SELECT {_JOB_COLUMNS} FROM jobs j JOIN companies c ON j.company_id = c.id"
            f"{clause}{order} LIMIT ? OFFSET ?",
            [*params, limit, offset],
        ).fetchall()
    return [_row_to_job(row, latest_start) for row in rows], total


def get_job(job_id: int) -> dict | None:
    with _conn() as conn:
        latest = conn.execute(
            "SELECT started_at FROM refresh_runs ORDER BY id DESC LIMIT 1"
        ).fetchone()
        row = conn.execute(
            "SELECT j.*, c.name AS company, c.h1b_approvals, c.sponsor_score"
            " FROM jobs j JOIN companies c ON j.company_id = c.id WHERE j.id = ?",
            (job_id,),
        ).fetchone()
    if row is None:
        return None
    return _row_to_job(row, latest["started_at"] if latest else None)


def set_status(job_id: int, status: str) -> None:
    if status not in VALID_STATUSES:
        raise ValueError(f"invalid status {status!r}")
    with _conn() as conn:
        cur = conn.execute("UPDATE jobs SET status = ? WHERE id = ?", (status, job_id))
        if cur.rowcount == 0:
            raise KeyError(f"no job with id {job_id}")
        if status == "applied":
            conn.execute(
                "UPDATE jobs SET stage = COALESCE(stage, 'applied'),"
                " applied_at = COALESCE(applied_at, ?),"
                " stage_updated_at = COALESCE(stage_updated_at, ?) WHERE id = ?",
                (_utcnow(), _utcnow(), job_id),
            )


def set_stage(job_id: int, stage: str) -> None:
    if stage not in APPLICATION_STAGES:
        raise ValueError(f"invalid stage {stage!r}")
    with _conn() as conn:
        cur = conn.execute(
            "UPDATE jobs SET stage = ?, stage_updated_at = ?,"
            " applied_at = COALESCE(applied_at, ?) WHERE id = ?",
            (stage, _utcnow(), _utcnow(), job_id),
        )
        if cur.rowcount == 0:
            raise KeyError(f"no job with id {job_id}")


def set_notes(job_id: int, notes: str) -> None:
    with _conn() as conn:
        cur = conn.execute(
            "UPDATE jobs SET notes = ? WHERE id = ?", (notes, job_id)
        )
        if cur.rowcount == 0:
            raise KeyError(f"no job with id {job_id}")


def application_analytics() -> dict:
    """Aggregates for the analytics page. 'Response' = any stage movement past
    'applied' (including rejection); 'interview' = interview or offer."""
    with _conn() as conn:
        applied = conn.execute(
            "SELECT COUNT(1) AS n FROM jobs WHERE applied_at IS NOT NULL"
        ).fetchone()["n"]
        by_stage = {
            row["stage"]: row["n"]
            for row in conn.execute(
                "SELECT stage, COUNT(1) AS n FROM jobs WHERE stage IS NOT NULL"
                " GROUP BY stage"
            ).fetchall()
        }
        responses = sum(v for k, v in by_stage.items() if k != "applied")
        interviews = sum(by_stage.get(k, 0) for k in ("interview", "offer"))
        by_source = [
            dict(row)
            for row in conn.execute(
                "SELECT j.source, COUNT(1) AS applied,"
                " SUM(CASE WHEN j.stage != 'applied' THEN 1 ELSE 0 END) AS responses,"
                " SUM(CASE WHEN j.stage IN ('interview','offer') THEN 1 ELSE 0 END) AS interviews"
                " FROM jobs j WHERE j.applied_at IS NOT NULL"
                " GROUP BY j.source ORDER BY applied DESC"
            ).fetchall()
        ]
        by_band = [
            dict(row)
            for row in conn.execute(
                "SELECT CASE WHEN j.match_score IS NULL THEN 'unscored'"
                " WHEN j.match_score >= 70 THEN '70+'"
                " WHEN j.match_score >= 50 THEN '50-69' ELSE '<50' END AS band,"
                " COUNT(1) AS applied,"
                " SUM(CASE WHEN j.stage != 'applied' THEN 1 ELSE 0 END) AS responses,"
                " SUM(CASE WHEN j.stage IN ('interview','offer') THEN 1 ELSE 0 END) AS interviews"
                " FROM jobs j WHERE j.applied_at IS NOT NULL"
                " GROUP BY band ORDER BY applied DESC"
            ).fetchall()
        ]
        by_week = [
            dict(row)
            for row in conn.execute(
                "SELECT strftime('%Y-W%W', applied_at) AS week, COUNT(1) AS applied"
                " FROM jobs WHERE applied_at IS NOT NULL"
                " GROUP BY week ORDER BY week DESC LIMIT 12"
            ).fetchall()
        ]
    return {
        "total_applied": applied,
        "by_stage": by_stage,
        "responses": responses,
        "interviews": interviews,
        "by_source": by_source,
        "by_band": by_band,
        "by_week": by_week,
    }


def set_match(job_id: int, score: float | None, match_json: str | None) -> None:
    with _conn() as conn:
        conn.execute(
            "UPDATE jobs SET match_score = ?, match_json = ? WHERE id = ?",
            (score, match_json, job_id),
        )


def set_classification(
    job_id: int, is_entry_level: bool, sponsorship: str, evidence: dict | None
) -> None:
    with _conn() as conn:
        conn.execute(
            "UPDATE jobs SET is_entry_level = ?, sponsorship = ?,"
            " sponsorship_evidence = ? WHERE id = ?",
            (
                1 if is_entry_level else 0,
                sponsorship,
                json.dumps(evidence) if evidence else None,
                job_id,
            ),
        )


def jobs_needing_classification() -> list[dict]:
    with _conn() as conn:
        rows = conn.execute(
            "SELECT j.id, j.title, j.description, c.name AS company,"
            " c.id AS company_id, c.h1b_approvals, c.name AS company_name"
            " FROM jobs j JOIN companies c ON j.company_id = c.id"
            " WHERE j.is_entry_level IS NULL"
        ).fetchall()
    return [dict(row) for row in rows]


def jobs_needing_score(limit: int = 150, include_basic: bool = False) -> list[dict]:
    """Unscored eligible entry-level jobs; with include_basic=True, also jobs
    whose stored score came from the local basic matcher (so LLM scoring
    upgrades them once a key exists)."""
    score_clause = "j.match_score IS NULL"
    if include_basic:
        score_clause = (
            "(j.match_score IS NULL"
            " OR json_extract(j.match_json, '$.method') = 'basic')"
        )
    with _conn() as conn:
        rows = conn.execute(
            "SELECT j.id, j.title, j.description, c.name AS company"
            " FROM jobs j JOIN companies c ON j.company_id = c.id"
            f" WHERE j.is_entry_level = 1 AND {score_clause}"
            " AND j.sponsorship != 'EXCLUDED'"  # never spend LLM quota on ineligible jobs
            " AND j.status NOT IN ('applied', 'hidden')"
            " ORDER BY COALESCE(j.posted_date, j.first_seen) DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [dict(row) for row in rows]


def get_setting(key: str) -> str | None:
    try:
        with _conn() as conn:
            row = conn.execute(
                "SELECT value FROM settings WHERE key = ?", (key,)
            ).fetchone()
    except sqlite3.OperationalError:  # pre-003 database without the table yet
        init_db()
        return None
    return row["value"] if row else None


def set_setting(key: str, value: str) -> None:
    init_db()  # tolerate pre-003 databases
    with _conn() as conn:
        conn.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?)"
            " ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )


def h1b_employer_count() -> int:
    with _conn() as conn:
        return conn.execute("SELECT COUNT(1) AS n FROM h1b_employers").fetchone()["n"]


def prune_old_jobs(days: int = 45) -> int:
    """Delete stale jobs the user never touched; Saved/Applied/Hidden history
    is never deleted. Returns the number of rows removed."""
    with _conn() as conn:
        cur = conn.execute(
            "DELETE FROM jobs WHERE status = 'none'"
            " AND date(COALESCE(posted_date, first_seen)) < date('now', ?)",
            (f"-{days} days",),
        )
        return cur.rowcount


def get_company_by_name(name: str) -> dict | None:
    with _conn() as conn:
        row = conn.execute("SELECT * FROM companies WHERE name = ?", (name,)).fetchone()
    return dict(row) if row else None


def store_h1b_employers(employers: dict) -> None:
    """Upsert normalized -> {display_name, approvals, lca_titles} records."""
    with _conn() as conn:
        for normalized, record in employers.items():
            conn.execute(
                "INSERT INTO h1b_employers (normalized_name, display_name, approvals,"
                " lca_titles) VALUES (?, ?, ?, ?)"
                " ON CONFLICT(normalized_name) DO UPDATE SET"
                " display_name=excluded.display_name, approvals=excluded.approvals,"
                " lca_titles=COALESCE(excluded.lca_titles, h1b_employers.lca_titles)",
                (
                    normalized,
                    record.get("display_name"),
                    int(record.get("approvals") or 0),
                    json.dumps(record["lca_titles"]) if record.get("lca_titles") else None,
                ),
            )


def load_h1b_employers() -> dict:
    with _conn() as conn:
        rows = conn.execute("SELECT * FROM h1b_employers").fetchall()
    return {
        row["normalized_name"]: {
            "display_name": row["display_name"],
            "approvals": row["approvals"],
            "lca_titles": json.loads(row["lca_titles"]) if row["lca_titles"] else None,
        }
        for row in rows
    }


def get_unchecked_companies() -> list[dict]:
    with _conn() as conn:
        rows = conn.execute(
            "SELECT id, name FROM companies WHERE sponsor_checked = 0"
        ).fetchall()
    return [dict(row) for row in rows]


def set_company_sponsorship(
    company_id: int,
    approvals: int,
    sponsor_score: str,
    lca_titles: list | None = None,
) -> None:
    with _conn() as conn:
        conn.execute(
            "UPDATE companies SET h1b_approvals=?, sponsor_score=?,"
            " lca_titles=COALESCE(?, lca_titles), sponsor_checked=1 WHERE id=?",
            (
                approvals,
                sponsor_score,
                json.dumps(lca_titles) if lca_titles else None,
                company_id,
            ),
        )


# --- refresh runs -----------------------------------------------------------


def start_run(trigger: str, force: bool = False) -> int | None:
    """Begin a refresh run. Returns run id, or None when blocked.

    Blocked when another run is active (always) or when the last run finished
    within the cooldown (unless force). An unfinished run older than
    STALE_RUN_MINUTES is treated as crashed and superseded.
    """
    now = datetime.now(timezone.utc)
    superseded_id = -1
    with _conn() as conn:
        active = conn.execute(
            "SELECT id, started_at FROM refresh_runs WHERE finished_at IS NULL"
            " ORDER BY id DESC LIMIT 1"
        ).fetchone()
        if active:
            age = now - _parse_ts(active["started_at"])
            if age < timedelta(minutes=STALE_RUN_MINUTES):
                return None
            superseded_id = active["id"]
            conn.execute(
                "UPDATE refresh_runs SET finished_at = ? WHERE id = ?",
                (_utcnow(), active["id"]),
            )
        if not force:
            last = conn.execute(
                "SELECT finished_at FROM refresh_runs WHERE finished_at IS NOT NULL"
                " AND id != ? ORDER BY id DESC LIMIT 1",
                (superseded_id,),
            ).fetchone()
            if last and now - _parse_ts(last["finished_at"]) < timedelta(
                minutes=COOLDOWN_MINUTES
            ):
                return None
        cur = conn.execute(
            "INSERT INTO refresh_runs (started_at, trigger) VALUES (?, ?)",
            (_utcnow(), trigger),
        )
        return cur.lastrowid


# update_run_source does a read-modify-write of the shared JSON status column;
# concurrent source threads must not interleave it or updates get lost.
_RUN_STATUS_LOCK = threading.Lock()


def update_run_source(run_id: int, source: str, **fields: Any) -> None:
    with _RUN_STATUS_LOCK, _conn() as conn:
        row = conn.execute(
            "SELECT source_status FROM refresh_runs WHERE id = ?", (run_id,)
        ).fetchone()
        if row is None:
            return
        status = json.loads(row["source_status"] or "{}")
        status.setdefault(source, {}).update(fields)
        conn.execute(
            "UPDATE refresh_runs SET source_status = ? WHERE id = ?",
            (json.dumps(status), run_id),
        )


def finish_run(run_id: int) -> None:
    with _conn() as conn:
        conn.execute(
            "UPDATE refresh_runs SET finished_at = ? WHERE id = ?",
            (_utcnow(), run_id),
        )


def get_run_status() -> dict:
    with _conn() as conn:
        row = conn.execute(
            "SELECT * FROM refresh_runs ORDER BY id DESC LIMIT 1"
        ).fetchone()
    if row is None:
        return {"active": False, "run_id": None, "sources": {}}
    return {
        "active": row["finished_at"] is None,
        "run_id": row["id"],
        "started_at": row["started_at"],
        "finished_at": row["finished_at"],
        "trigger": row["trigger"],
        "sources": json.loads(row["source_status"] or "{}"),
    }


def _force_run_started_at(run_id: int, started_at: str) -> None:
    """Test helper: backdate a run's start time."""
    with _conn() as conn:
        conn.execute(
            "UPDATE refresh_runs SET started_at = ? WHERE id = ?", (started_at, run_id)
        )


# --- user profile -----------------------------------------------------------

_PROFILE_JSON_FIELDS = ("skills", "target_locations", "preferences")


def get_profile() -> dict | None:
    with _conn() as conn:
        row = conn.execute("SELECT * FROM user_profile WHERE id = 1").fetchone()
    if row is None:
        return None
    profile = dict(row)
    for field in _PROFILE_JSON_FIELDS:
        profile[field] = json.loads(profile[field]) if profile[field] else []
    if not isinstance(profile["preferences"], dict):
        profile["preferences"] = {}
    return profile


def save_profile(**fields: Any) -> None:
    """Create or partially update the single profile row (id=1)."""
    with _conn() as conn:
        existing = conn.execute(
            "SELECT * FROM user_profile WHERE id = 1"
        ).fetchone()
        current = dict(existing) if existing else {
            "resume_text": None, "resume_filename": None, "skills": None,
            "target_locations": None, "preferences": None,
        }
        for key, value in fields.items():
            if key in _PROFILE_JSON_FIELDS and value is not None:
                value = json.dumps(value)
            current[key] = value
        conn.execute(
            "INSERT INTO user_profile (id, resume_text, resume_filename, skills,"
            " target_locations, preferences, updated_at)"
            " VALUES (1, ?, ?, ?, ?, ?, ?)"
            " ON CONFLICT(id) DO UPDATE SET resume_text=excluded.resume_text,"
            " resume_filename=excluded.resume_filename, skills=excluded.skills,"
            " target_locations=excluded.target_locations,"
            " preferences=excluded.preferences, updated_at=excluded.updated_at",
            (
                current["resume_text"],
                current["resume_filename"],
                current["skills"],
                current["target_locations"],
                current["preferences"],
                _utcnow(),
            ),
        )
