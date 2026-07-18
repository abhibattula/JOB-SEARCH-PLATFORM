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
