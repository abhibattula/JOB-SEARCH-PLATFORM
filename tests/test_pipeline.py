"""T013: refresh orchestration — per-source isolation, run records, cooldown."""
import pytest

from engine import db, pipeline
from engine.ingest.base import RawJob


def fake_source(name, jobs=None, error=None):
    class Module:
        SOURCE_NAME = name

        @staticmethod
        def fetch_jobs(entries):
            if error:
                raise error
            return jobs or []

    return Module


def raw(title, url, source):
    return RawJob(title=title, company="TestCo", url=url, source=source)


@pytest.fixture()
def fake_sources(monkeypatch, tmp_db):
    good = fake_source(
        "good",
        jobs=[raw("Engineer A", "https://x.example/a", "good"),
              raw("Engineer B", "https://x.example/b", "good")],
    )
    bad = fake_source("bad", error=RuntimeError("boom"))
    modules = {"good": good, "bad": bad}
    monkeypatch.setattr(pipeline, "_source_names", lambda: ["good", "bad"])
    monkeypatch.setattr(pipeline, "_get_source", lambda name: modules[name])
    monkeypatch.setattr(pipeline, "load_companies", lambda: [])
    return modules


class TestRunRefresh:
    def test_failure_isolated_and_run_recorded(self, fake_sources):
        summary = pipeline.run_refresh(trigger="cli")
        assert summary["started"] is True
        assert summary["sources"]["good"]["state"] == "done"
        assert summary["sources"]["good"]["added"] == 2
        assert summary["sources"]["bad"]["state"] == "failed"
        assert "boom" in summary["sources"]["bad"]["error"]
        _, total = db.query_jobs(window=None)
        assert total == 2
        assert db.get_run_status()["active"] is False

    def test_cooldown_blocks_second_run(self, fake_sources):
        assert pipeline.run_refresh(trigger="auto")["started"] is True
        blocked = pipeline.run_refresh(trigger="auto")
        assert blocked["started"] is False
        assert blocked["reason"] == "cooldown"

    def test_force_bypasses_cooldown(self, fake_sources):
        pipeline.run_refresh(trigger="auto")
        forced = pipeline.run_refresh(trigger="manual", force=True)
        assert forced["started"] is True


class TestScoringStage:
    @pytest.fixture()
    def entry_source(self, monkeypatch, tmp_db):
        source = fake_source(
            "good",
            jobs=[
                raw("Software Engineer, New Grad", "https://x.example/ng", "good"),
                raw("Senior Software Engineer", "https://x.example/sr", "good"),
            ],
        )
        monkeypatch.setattr(pipeline, "_source_names", lambda: ["good"])
        monkeypatch.setattr(pipeline, "_get_source", lambda name: source)
        monkeypatch.setattr(pipeline, "load_companies", lambda: [])
        db.save_profile(resume_text="my resume", resume_filename="r.pdf")
        return source

    def test_entry_level_jobs_scored_when_resume_present(self, entry_source, monkeypatch):
        from engine import matcher

        monkeypatch.setenv("LLM_API_KEY", "test")
        monkeypatch.setattr(
            pipeline,
            "_analyze",
            lambda *a: matcher.MatchAnalysis(match_score=81, reasoning="ok"),
        )
        pipeline.run_refresh(trigger="cli")
        jobs, _ = db.query_jobs(window=None, statuses=None, entry_level=True)
        assert len(jobs) == 1  # senior job excluded by classifier
        assert jobs[0]["match_score"] == 81

    def test_analysis_failure_leaves_job_visible_unscored(self, entry_source, monkeypatch):
        monkeypatch.setenv("LLM_API_KEY", "test")
        monkeypatch.setattr(pipeline, "_analyze", lambda *a: None)
        pipeline.run_refresh(trigger="cli")
        jobs, _ = db.query_jobs(window=None, statuses=None, entry_level=True)
        assert len(jobs) == 1
        assert jobs[0]["match_score"] is None
