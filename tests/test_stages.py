"""004-WS-C: application stages, follow-up flags, response analytics."""
from datetime import datetime, timedelta, timezone

import pytest

from engine import db


def seed(url, title="Engineer"):
    db.upsert_job(
        {"title": title, "company": "TestCo", "url": url, "source": "greenhouse"}
    )
    jobs, _ = db.query_jobs(window=None, statuses=None, entry_level=None)
    return next(j for j in jobs if j["url"] == url)["id"]


def backdate_stage(job_id, days):
    stale = (datetime.now(timezone.utc) - timedelta(days=days)).strftime(
        "%Y-%m-%d %H:%M:%S.000"
    )
    with db._conn() as conn:
        conn.execute(
            "UPDATE jobs SET stage_updated_at = ? WHERE id = ?", (stale, job_id)
        )


class TestStages:
    def test_marking_applied_sets_stage_and_date(self, tmp_db):
        job_id = seed("u1")
        db.set_status(job_id, "applied")
        job = db.get_job(job_id)
        assert job["stage"] == "applied"
        assert job["applied_at"] is not None

    def test_stage_transitions(self, tmp_db):
        job_id = seed("u1")
        db.set_status(job_id, "applied")
        db.set_stage(job_id, "interview")
        assert db.get_job(job_id)["stage"] == "interview"
        with pytest.raises(ValueError):
            db.set_stage(job_id, "hired-instantly")
        with pytest.raises(KeyError):
            db.set_stage(99999, "oa")

    def test_notes_roundtrip(self, tmp_db):
        job_id = seed("u1")
        db.set_notes(job_id, "Spoke to recruiter Sam; OA due Friday")
        assert "recruiter Sam" in db.get_job(job_id)["notes"]

    def test_follow_up_flag_after_seven_quiet_days(self, tmp_db):
        fresh = seed("u1", "Fresh Application")
        stale = seed("u2", "Stale Application")
        db.set_status(fresh, "applied")
        db.set_status(stale, "applied")
        backdate_stage(stale, days=9)

        rows, _ = db.query_jobs(window=None, statuses=["applied"])
        by_id = {j["id"]: j for j in rows}
        assert by_id[stale]["follow_up"] is True
        assert by_id[fresh]["follow_up"] is False


class TestAnalytics:
    def test_aggregates(self, tmp_db):
        specs = [
            ("a1", "applied"), ("a2", "oa"), ("a3", "interview"),
            ("a4", "rejected"), ("a5", "offer"),
        ]
        for url, stage in specs:
            job_id = seed(url, f"Job {url}")
            db.set_status(job_id, "applied")
            if stage != "applied":
                db.set_stage(job_id, stage)
        stats = db.application_analytics()
        assert stats["total_applied"] == 5
        assert stats["by_stage"]["interview"] == 1
        assert stats["responses"] == 4       # any movement past 'applied'
        assert stats["interviews"] == 2      # interview + offer
        assert stats["by_source"][0]["source"] == "greenhouse"
        assert stats["by_source"][0]["applied"] == 5
