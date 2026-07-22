"""T004: dedup, recency queries, status transitions, refresh-run cooldown."""
from datetime import datetime, timedelta, timezone

import pytest

from engine import db


def make_job(**overrides):
    job = {
        "title": "Software Engineer, New Grad",
        "company": "Stripe",
        "url": "https://boards.greenhouse.io/stripe/jobs/1",
        "source": "greenhouse",
        "location": "San Francisco, CA",
        "is_remote": False,
        "description": "Build payments infrastructure.",
        "posted_date": "2026-07-15",
    }
    job.update(overrides)
    return job


def iso_days_ago(days, hours=0):
    return (
        datetime.now(timezone.utc) - timedelta(days=days, hours=hours)
    ).strftime("%Y-%m-%d")


class TestInit:
    def test_init_is_idempotent(self, tmp_db):
        db.init_db()
        db.init_db()
        jobs, total = db.query_jobs()
        assert jobs == [] and total == 0


class TestUpsert:
    def test_insert_then_update_same_url(self, tmp_db):
        assert db.upsert_job(make_job()) == "inserted"
        result = db.upsert_job(
            make_job(description="Updated text.", posted_date="2026-07-16")
        )
        assert result == "updated"
        jobs, total = db.query_jobs()
        assert total == 1
        job = db.get_job(jobs[0]["id"])
        assert job["description"] == "Updated text."
        assert job["posted_date"] == "2026-07-16"

    def test_first_seen_never_changes_on_update(self, tmp_db):
        db.upsert_job(make_job())
        jobs, _ = db.query_jobs()
        first_seen_before = db.get_job(jobs[0]["id"])["first_seen"]
        db.upsert_job(make_job(description="new"))
        assert db.get_job(jobs[0]["id"])["first_seen"] == first_seen_before

    def test_status_and_score_preserved_on_update(self, tmp_db):
        db.upsert_job(make_job())
        jobs, _ = db.query_jobs()
        job_id = jobs[0]["id"]
        db.set_status(job_id, "saved")
        db.set_match(job_id, 88.0, '{"match_score": 88}')
        db.upsert_job(make_job(description="refreshed"))
        job = db.get_job(job_id)
        assert job["status"] == "saved"
        assert job["match_score"] == 88.0

    def test_cross_source_dedup_key_collapses_duplicates(self, tmp_db):
        db.upsert_job(make_job())
        result = db.upsert_job(
            make_job(
                url="https://www.indeed.com/viewjob?jk=abc",
                source="jobspy",
            )
        )
        assert result == "skipped"
        _, total = db.query_jobs()
        assert total == 1

    def test_company_row_created_on_the_fly(self, tmp_db):
        db.upsert_job(make_job(company="Mystery Startup", url="https://x.example/1"))
        company = db.get_company_by_name("Mystery Startup")
        assert company is not None
        assert company["ats_type"] is None


class TestRecency:
    def test_windows_use_posted_date_with_first_seen_fallback(self, tmp_db):
        db.upsert_job(make_job(url="u1", posted_date=iso_days_ago(2)))
        db.upsert_job(make_job(url="u2", posted_date=iso_days_ago(10)))
        db.upsert_job(make_job(url="u3", posted_date=None))  # falls back to first_seen=now
        db.upsert_job(make_job(url="u4", posted_date=iso_days_ago(0)))

        week, total_week = db.query_jobs(window="7d")
        assert total_week == 3  # u2 is 10 days old
        urls = {j["url"] for j in week}
        assert urls == {"u1", "u3", "u4"}

        day, total_day = db.query_jobs(window="24h")
        assert {j["url"] for j in day} == {"u3", "u4"}

    def test_no_window_returns_everything(self, tmp_db):
        db.upsert_job(make_job(url="u1", posted_date=iso_days_ago(40)))
        _, total = db.query_jobs(window=None)
        assert total == 1


class TestStatus:
    def test_default_feed_hides_applied_and_hidden_keeps_saved(self, tmp_db):
        for i, status in enumerate(["none", "saved", "applied", "hidden"]):
            db.upsert_job(make_job(url=f"u{i}", title=f"Job {i}"))
            jobs, _ = db.query_jobs()
        all_jobs, _ = db.query_jobs(statuses=None, window=None)
        ids = {j["url"]: j["id"] for j in all_jobs}
        db.set_status(ids["u1"], "saved")
        db.set_status(ids["u2"], "applied")
        db.set_status(ids["u3"], "hidden")

        default, total = db.query_jobs()
        assert {j["url"] for j in default} == {"u0", "u1"}

        applied, _ = db.query_jobs(statuses=["applied"])
        assert {j["url"] for j in applied} == {"u2"}

    def test_invalid_status_rejected(self, tmp_db):
        db.upsert_job(make_job())
        jobs, _ = db.query_jobs()
        with pytest.raises(ValueError):
            db.set_status(jobs[0]["id"], "bogus")

    def test_unknown_job_rejected(self, tmp_db):
        with pytest.raises(KeyError):
            db.set_status(99999, "saved")


class TestRefreshRuns:
    def test_single_flight_blocks_second_start(self, tmp_db):
        run_id = db.start_run("auto")
        assert run_id is not None
        assert db.start_run("auto") is None
        db.finish_run(run_id)

    def test_cooldown_blocks_auto_but_not_force(self, tmp_db):
        run_id = db.start_run("auto")
        db.finish_run(run_id)
        assert db.start_run("auto") is None  # finished moments ago -> cooldown
        forced = db.start_run("manual", force=True)
        assert forced is not None
        db.finish_run(forced)

    def test_stale_unfinished_run_is_superseded(self, tmp_db):
        run_id = db.start_run("auto")
        stale = (
            datetime.now(timezone.utc) - timedelta(minutes=45)
        ).isoformat()
        db._force_run_started_at(run_id, stale)  # test helper
        new_run = db.start_run("auto")
        assert new_run is not None and new_run != run_id
        db.finish_run(new_run)

    def test_run_status_reports_sources(self, tmp_db):
        run_id = db.start_run("cli")
        db.update_run_source(run_id, "greenhouse", state="done", found=10, added=3)
        status = db.get_run_status()
        assert status["active"] is True
        assert status["sources"]["greenhouse"]["added"] == 3
        db.finish_run(run_id)
        assert db.get_run_status()["active"] is False

    def test_is_new_flags_jobs_from_latest_run(self, tmp_db):
        db.upsert_job(make_job(url="old"))
        run_id = db.start_run("auto")
        db.upsert_job(make_job(url="fresh", title="Fresh Job"))
        jobs, _ = db.query_jobs()
        by_url = {j["url"]: j for j in jobs}
        assert by_url["fresh"]["is_new"] is True
        assert by_url["old"]["is_new"] is False
        db.finish_run(run_id)

    def test_utcnow_has_microsecond_resolution(self):
        """v0.6.1 regression (mac CI): _utcnow() truncated to milliseconds,
        so on a fast runner upsert_job() and start_run() could land in the
        same millisecond — making a pre-run job's first_seen equal to the
        run's started_at, and is_new's inclusive >= flagged it as new.
        Full microsecond precision keeps sequential calls distinct."""
        stamp = db._utcnow()
        fractional = stamp.rsplit(".", 1)[1]
        assert len(fractional) == 6, stamp
        # and it must still round-trip through the parser used everywhere
        assert db._parse_ts(stamp).microsecond == int(fractional)


class TestEligibility:
    def _seed_with_sponsorship(self):
        for i, rating in enumerate(["HIGH", "UNKNOWN", "EXCLUDED", "EXCLUDED"]):
            db.upsert_job(make_job(url=f"e{i}", title=f"Engineer {chr(65 + i)}"))
        jobs, _ = db.query_jobs(window=None, statuses=None, include_ineligible=True)
        for job, rating in zip(sorted(jobs, key=lambda j: j["url"]),
                               ["HIGH", "UNKNOWN", "EXCLUDED", "EXCLUDED"]):
            db.set_classification(job["id"], True, rating, None)

    def test_default_feed_hides_excluded(self, tmp_db):
        self._seed_with_sponsorship()
        jobs, total = db.query_jobs(window=None)
        assert total == 2
        assert all(j["sponsorship"] != "EXCLUDED" for j in jobs)

    def test_ineligible_view_shows_only_excluded(self, tmp_db):
        self._seed_with_sponsorship()
        jobs, total = db.query_jobs(window=None, ineligible=True)
        assert total == 2
        assert all(j["sponsorship"] == "EXCLUDED" for j in jobs)

    def test_excluded_jobs_never_scored(self, tmp_db):
        self._seed_with_sponsorship()
        candidates = db.jobs_needing_score()
        assert len(candidates) == 2  # the two eligible entry-level jobs only


class TestMinScore:
    def _seed_scored(self):
        for i, score in enumerate([90.0, 72.0, 45.0, None]):
            db.upsert_job(make_job(url=f"s{i}", title=f"Scored {i}"))
        jobs, _ = db.query_jobs(window=None, statuses=None)
        for job, score in zip(sorted(jobs, key=lambda j: j["url"]),
                              [90.0, 72.0, 45.0, None]):
            if score is not None:
                db.set_match(job["id"], score, "{}")

    def test_threshold_filters_and_drops_unscored(self, tmp_db):
        self._seed_scored()
        jobs, total = db.query_jobs(window=None, min_score=70)
        assert total == 2
        assert {j["url"] for j in jobs} == {"s0", "s1"}

    def test_no_threshold_keeps_unscored(self, tmp_db):
        self._seed_scored()
        _, total = db.query_jobs(window=None)
        assert total == 4


class TestPrune:
    def test_prunes_stale_untouched_jobs_only(self, tmp_db):
        db.upsert_job(make_job(url="fresh", posted_date=iso_days_ago(2)))
        db.upsert_job(make_job(url="stale", title="Old Job", posted_date=iso_days_ago(60)))
        db.upsert_job(make_job(url="stale-saved", title="Old Saved", posted_date=iso_days_ago(60)))
        jobs, _ = db.query_jobs(window=None, statuses=None)
        ids = {j["url"]: j["id"] for j in jobs}
        db.set_status(ids["stale-saved"], "applied")

        removed = db.prune_old_jobs(days=45)
        assert removed == 1
        remaining, _ = db.query_jobs(window=None, statuses=None, include_ineligible=True)
        urls = {j["url"] for j in remaining}
        assert urls == {"fresh", "stale-saved"}


class TestProfile:
    def test_profile_roundtrip(self, tmp_db):
        assert db.get_profile() is None
        db.save_profile(
            resume_text="text",
            resume_filename="resume.pdf",
            skills=["python", "verilog"],
            target_locations=["CA", "Remote"],
        )
        profile = db.get_profile()
        assert profile["skills"] == ["python", "verilog"]
        db.save_profile(target_locations=["TX"])
        profile = db.get_profile()
        assert profile["target_locations"] == ["TX"]
        assert profile["resume_text"] == "text"  # partial update preserved

    def test_profile_identity_fields_roundtrip(self, tmp_db):
        """006-A: first_name/last_name/phone/linkedin_url/portfolio_url —
        confirmed gap: engine/autofill/browser_controller.py already reads
        these via profile.get(...), but the schema never had them, so
        Apply Assist could never fill them."""
        db.save_profile(
            first_name="Ada", last_name="Lovelace", phone="555-0100",
            email="ada@example.com",
            linkedin_url="https://linkedin.com/in/ada",
            portfolio_url="https://ada.example.com",
        )
        profile = db.get_profile()
        assert profile["first_name"] == "Ada"
        assert profile["last_name"] == "Lovelace"
        assert profile["phone"] == "555-0100"
        assert profile["email"] == "ada@example.com"
        assert profile["linkedin_url"] == "https://linkedin.com/in/ada"
        assert profile["portfolio_url"] == "https://ada.example.com"
        # A later partial update must not clobber the others
        db.save_profile(phone="555-0199")
        profile = db.get_profile()
        assert profile["phone"] == "555-0199"
        assert profile["first_name"] == "Ada"

    def test_profile_resume_builder_fields_roundtrip(self, tmp_db):
        """007-T004: resume_file_path (stored original upload),
        resume_sections (structured JSON), sections_edited_at (drives the
        keep-vs-re-extract prompt)."""
        sections = {
            "experience": [{"title": "Intern", "organization": "Acme",
                            "start": "2025-05", "end": "2025-08",
                            "bullets": ["Built firmware"]}],
            "education": [], "projects": [], "skills": ["python"],
        }
        db.save_profile(
            resume_file_path="C:/data/resume/r.pdf",
            resume_sections=sections,
            sections_edited_at="2026-07-21 12:00:00.000000",
        )
        profile = db.get_profile()
        assert profile["resume_file_path"] == "C:/data/resume/r.pdf"
        assert profile["resume_sections"] == sections  # JSON roundtrip
        assert profile["sections_edited_at"] == "2026-07-21 12:00:00.000000"
        # partial update must not clobber the sections
        db.save_profile(resume_file_path="C:/data/resume/r2.pdf")
        profile = db.get_profile()
        assert profile["resume_sections"] == sections
        assert profile["resume_file_path"] == "C:/data/resume/r2.pdf"

    def test_profile_sponsorship_and_visa_fields_roundtrip(self, tmp_db):
        """005-T008: user_profile gains authorized_without_sponsorship/visa_status
        so answer_bank.suggest() can ground drafts in facts the user provided."""
        db.save_profile(
            resume_text="text",
            authorized_without_sponsorship="no",
            visa_status="OPT",
        )
        profile = db.get_profile()
        assert profile["authorized_without_sponsorship"] == "no"
        assert profile["visa_status"] == "OPT"
        db.save_profile(visa_status="H-1B")
        assert db.get_profile()["visa_status"] == "H-1B"


class TestSponsorIntelColumns:
    """007-T004: sponsorship-intelligence columns land via _MIGRATIONS —
    companies (denials, wage medians, cap_exempt, sponsor_grade) and
    h1b_employers (denials, wage medians)."""

    def test_companies_gain_grade_columns(self, tmp_db):
        with db._conn() as conn:
            cid = db._get_or_create_company(conn, "GradeCo")
            conn.execute(
                "UPDATE companies SET h1b_denials=?, wage_level_median=?,"
                " wage_offered_median=?, cap_exempt=?, sponsor_grade=?"
                " WHERE id=?",
                (7, "III", 145000.0, 0, "B", cid),
            )
            row = conn.execute(
                "SELECT * FROM companies WHERE id=?", (cid,)
            ).fetchone()
        assert row["h1b_denials"] == 7
        assert row["wage_level_median"] == "III"
        assert row["wage_offered_median"] == 145000.0
        assert row["cap_exempt"] == 0
        assert row["sponsor_grade"] == "B"

    def test_h1b_employers_gain_wage_denial_columns(self, tmp_db):
        with db._conn() as conn:
            conn.execute(
                "INSERT INTO h1b_employers (normalized_name, display_name,"
                " approvals, denials, wage_level_median, wage_offered_median)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                ("gradeco", "GradeCo", 40, 5, "IV", 160000.0),
            )
            row = conn.execute(
                "SELECT * FROM h1b_employers WHERE normalized_name='gradeco'"
            ).fetchone()
        assert row["denials"] == 5
        assert row["wage_level_median"] == "IV"
        assert row["wage_offered_median"] == 160000.0


class TestAnswerBank:
    """005-T008: answer_bank + application_answers tables (data-model.md)."""

    def test_answer_bank_schema_has_expected_columns(self, tmp_db):
        with db._conn() as conn:
            cols = {row["name"] for row in conn.execute("PRAGMA table_info(answer_bank)")}
        assert cols == {
            "id", "question_normalized", "question_raw", "answer",
            "category", "source", "confirmed_at", "updated_at",
        }

    def test_answer_bank_question_normalized_is_unique(self, tmp_db):
        with db._conn() as conn:
            conn.execute(
                "INSERT INTO answer_bank (question_normalized, question_raw, answer,"
                " category, source, confirmed_at, updated_at) VALUES (?,?,?,?,?,?,?)",
                ("authorized to work", "Are you authorized to work?", "Yes",
                 "work_authorization", "user", "2026-07-20 00:00:00.000",
                 "2026-07-20 00:00:00.000"),
            )
        with db._conn() as conn:
            with pytest.raises(Exception):
                conn.execute(
                    "INSERT INTO answer_bank (question_normalized, question_raw, answer,"
                    " category, source, confirmed_at, updated_at) VALUES (?,?,?,?,?,?,?)",
                    ("authorized to work", "dup", "dup", None, "user",
                     "2026-07-20 00:00:00.000", "2026-07-20 00:00:00.000"),
                )

    def test_application_answers_schema_and_fk(self, tmp_db):
        db.upsert_job(make_job())
        jobs, _ = db.query_jobs()
        job_id = jobs[0]["id"]
        with db._conn() as conn:
            cols = {row["name"] for row in conn.execute("PRAGMA table_info(application_answers)")}
            assert cols == {
                "id", "job_id", "answer_bank_id", "question_raw",
                "answer_used", "answered_at",
            }
            conn.execute(
                "INSERT INTO application_answers (job_id, answer_bank_id, question_raw,"
                " answer_used, answered_at) VALUES (?,?,?,?,?)",
                (job_id, None, "Are you authorized to work?", "Yes",
                 "2026-07-20 00:00:00.000"),
            )
        with db._conn() as conn:
            row = conn.execute(
                "SELECT * FROM application_answers WHERE job_id = ?", (job_id,)
            ).fetchone()
        assert row["answer_used"] == "Yes"


# --- 008: migrations, backfill, backup-before-migrate ------------------------

import sqlite3

# A faithful v0.7.0-shape database (original _SCHEMA + all pre-008 migration
# columns, none of the 008 ones). Used by the migration tests here and by the
# upgrade-with-data release gate (T051).
_V07_SCHEMA = """
CREATE TABLE companies (id INTEGER PRIMARY KEY, name TEXT UNIQUE NOT NULL,
    normalized_name TEXT, ats_type TEXT, ats_slug TEXT,
    h1b_approvals INTEGER DEFAULT 0, lca_titles TEXT,
    sponsor_score TEXT DEFAULT 'UNKNOWN', sponsor_checked INTEGER DEFAULT 0,
    h1b_denials INTEGER DEFAULT 0, wage_level_median TEXT,
    wage_offered_median REAL, cap_exempt INTEGER DEFAULT 0, sponsor_grade TEXT);
CREATE TABLE jobs (id INTEGER PRIMARY KEY, company_id INTEGER NOT NULL,
    title TEXT NOT NULL, location TEXT, is_remote INTEGER DEFAULT 0,
    description TEXT, url TEXT UNIQUE NOT NULL, dedup_key TEXT,
    source TEXT NOT NULL, posted_date TEXT, first_seen TEXT NOT NULL,
    is_entry_level INTEGER, sponsorship TEXT DEFAULT 'UNKNOWN',
    sponsorship_evidence TEXT, match_score REAL, match_json TEXT,
    status TEXT DEFAULT 'none', tailor_json TEXT, stage TEXT, applied_at TEXT,
    stage_updated_at TEXT, notes TEXT);
CREATE TABLE user_profile (id INTEGER PRIMARY KEY, resume_text TEXT,
    resume_filename TEXT, skills TEXT, target_locations TEXT, preferences TEXT,
    updated_at TEXT, authorized_without_sponsorship TEXT, visa_status TEXT,
    first_name TEXT, last_name TEXT, email TEXT, phone TEXT, linkedin_url TEXT,
    portfolio_url TEXT, resume_file_path TEXT, resume_sections TEXT,
    sections_edited_at TEXT);
CREATE TABLE refresh_runs (id INTEGER PRIMARY KEY, started_at TEXT NOT NULL,
    finished_at TEXT, trigger TEXT, source_status TEXT DEFAULT '{}');
CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE h1b_employers (normalized_name TEXT PRIMARY KEY, display_name TEXT,
    approvals INTEGER DEFAULT 0, lca_titles TEXT, denials INTEGER DEFAULT 0,
    wage_level_median TEXT, wage_offered_median REAL);
CREATE TABLE answer_bank (id INTEGER PRIMARY KEY,
    question_normalized TEXT UNIQUE NOT NULL, question_raw TEXT NOT NULL,
    answer TEXT NOT NULL, category TEXT, source TEXT DEFAULT 'user',
    confirmed_at TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE TABLE application_answers (id INTEGER PRIMARY KEY,
    job_id INTEGER NOT NULL, answer_bank_id INTEGER, question_raw TEXT NOT NULL,
    answer_used TEXT NOT NULL, answered_at TEXT NOT NULL);
"""


def make_v07_db(path):
    conn = sqlite3.connect(path)
    conn.executescript(_V07_SCHEMA)
    conn.execute(
        "INSERT INTO companies (id, name, normalized_name) VALUES (1, 'Stripe', 'stripe')"
    )
    conn.execute(
        "INSERT INTO jobs (company_id, title, url, source, first_seen, status,"
        " match_score) VALUES (1, 'SWE New Grad', 'https://x/1', 'greenhouse',"
        " '2026-07-20 10:00:00.000000', 'saved', 82.0)"
    )
    conn.execute(
        "INSERT INTO user_profile (id, first_name, skills) VALUES"
        " (1, 'Abhinav', '[\"python\"]')"
    )
    conn.commit()
    conn.close()


class TestMigrations008:
    def test_new_columns_and_watchlist_table_exist(self, tmp_db):
        with db._conn() as conn:
            job_cols = {r["name"] for r in conn.execute("PRAGMA table_info(jobs)")}
            assert {"last_seen_at", "delisted", "embedding"} <= job_cols
            prof_cols = {
                r["name"] for r in conn.execute("PRAGMA table_info(user_profile)")
            }
            assert {"search_terms", "resume_embedding"} <= prof_cols
            tables = {
                r["name"]
                for r in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
            }
            assert "watchlist" in tables

    def test_v07_upgrade_backfills_last_seen_and_preserves_data(self, _isolated_db):
        make_v07_db(_isolated_db)
        db.init_db()
        with db._conn() as conn:
            row = conn.execute("SELECT * FROM jobs").fetchone()
            assert row["last_seen_at"] == row["first_seen"]
            assert row["delisted"] == 0
            assert row["status"] == "saved" and row["match_score"] == 82.0
            prof = conn.execute("SELECT * FROM user_profile").fetchone()
            assert prof["first_name"] == "Abhinav"

    def test_backup_created_before_migration(self, _isolated_db):
        make_v07_db(_isolated_db)
        db.init_db()
        backups = list((_isolated_db.parent / "backup").glob("*.db"))
        assert len(backups) == 1
        check = sqlite3.connect(backups[0])
        check.row_factory = sqlite3.Row
        row = check.execute("SELECT * FROM jobs").fetchone()
        cols = {r["name"] for r in check.execute("PRAGMA table_info(jobs)")}
        check.close()
        assert row["title"] == "SWE New Grad"
        assert "last_seen_at" not in cols  # pre-migration snapshot

    def test_no_backup_when_nothing_pending(self, _isolated_db):
        db.init_db()  # fresh db: no file existed, nothing to back up
        db.init_db()  # idempotent re-run: still nothing pending
        backup_dir = _isolated_db.parent / "backup"
        assert not backup_dir.exists() or not list(backup_dir.glob("*.db"))

    def test_restore_on_migration_failure(self, _isolated_db, monkeypatch):
        make_v07_db(_isolated_db)

        def boom(conn):
            raise RuntimeError("migration exploded")

        monkeypatch.setattr(db, "_apply_migrations", boom)
        with pytest.raises(RuntimeError):
            db.init_db()
        # original file restored: old shape, data intact
        check = sqlite3.connect(_isolated_db)
        check.row_factory = sqlite3.Row
        cols = {r["name"] for r in check.execute("PRAGMA table_info(jobs)")}
        count = check.execute("SELECT COUNT(*) c FROM jobs").fetchone()["c"]
        check.close()
        assert "last_seen_at" not in cols
        assert count == 1
