"""008 US3 (T024/T026): dead-posting detection.

Board-diff delisting: full-board ATS sources fetch entire boards, so a job
absent from a SUCCESSFULLY fetched board is authoritatively gone (FR-013).
A failed/errored fetch must never mass-delist. Scraped-board rows (jobspy)
get a throttled HEAD liveness check instead.
"""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from engine import db, pipeline, watchlist
from engine.ingest.base import RawJob


def seed_board_job(url, slug="stripe", company="Stripe", source="greenhouse",
                   title="SWE", posted_days_ago=2):
    posted = (datetime.now(timezone.utc) - timedelta(days=posted_days_ago)).strftime("%Y-%m-%d")
    db.upsert_job({
        "title": title, "company": company, "url": url, "source": source,
        "location": "SF", "description": "d", "posted_date": posted,
        "company_ats_type": source, "company_ats_slug": slug,
    })


def job_by_url(url):
    jobs, _ = db.query_jobs(window=None, statuses=None, entry_level=None)
    return next(j for j in jobs if j["url"] == url)


class TestBoardDiffDelisting:
    def test_absent_job_delisted_when_board_fetch_succeeded(self, tmp_db):
        watchlist.add("greenhouse", "stripe", name="Stripe")
        seed_board_job("https://gh/1", title="Role A")
        seed_board_job("https://gh/2", title="Role B")
        run_id = db.start_run("manual", force=True)
        seed_board_job("https://gh/1", title="Role A")  # still on the board
        watchlist.mark_ok("greenhouse", "stripe")
        db.update_run_source(run_id, "greenhouse", state="done")
        delisted = pipeline.delist_missing(run_id)
        assert delisted == 1
        assert job_by_url("https://gh/2")["delisted"] is True
        assert job_by_url("https://gh/1")["delisted"] is False

    def test_failed_board_fetch_never_delists(self, tmp_db):
        watchlist.add("greenhouse", "stripe", name="Stripe")
        seed_board_job("https://gh/1", title="Role A")
        run_id = db.start_run("manual", force=True)
        # board fetch failed: no mark_ok this run, source errored
        db.update_run_source(run_id, "greenhouse", state="failed", error="boom")
        assert pipeline.delist_missing(run_id) == 0
        assert job_by_url("https://gh/1")["delisted"] is False

    def test_done_source_with_unfetched_board_does_not_delist_that_board(
        self, tmp_db
    ):
        """One company's board 404ing inside an otherwise-successful source
        run must not delist that company's jobs."""
        watchlist.add("greenhouse", "stripe", name="Stripe")
        watchlist.add("greenhouse", "figma", name="Figma")
        seed_board_job("https://gh/s1", slug="stripe", company="Stripe", title="Role A")
        seed_board_job("https://gh/f1", slug="figma", company="Figma", title="Role B")
        run_id = db.start_run("manual", force=True)
        watchlist.mark_ok("greenhouse", "stripe")  # figma's fetch failed
        db.update_run_source(run_id, "greenhouse", state="done")
        assert pipeline.delist_missing(run_id) == 1
        assert job_by_url("https://gh/s1")["delisted"] is True
        assert job_by_url("https://gh/f1")["delisted"] is False

    def test_scraped_sources_are_never_board_diffed(self, tmp_db):
        seed_board_job("https://indeed/1", source="jobspy", slug=None, title="Role A")
        run_id = db.start_run("manual", force=True)
        db.update_run_source(run_id, "jobspy", state="done")
        assert pipeline.delist_missing(run_id) == 0
        assert job_by_url("https://indeed/1")["delisted"] is False


class TestIngestAgeGate:
    def test_jobs_older_than_14_days_are_not_ingested(self, tmp_db, monkeypatch):
        old = (datetime.now(timezone.utc) - timedelta(days=20)).strftime("%Y-%m-%d")
        fresh = (datetime.now(timezone.utc) - timedelta(days=3)).strftime("%Y-%m-%d")

        class FakeSource:
            @staticmethod
            def fetch_jobs(entries):
                yield RawJob(title="Old Role", company="A", url="https://x/old",
                             source="fake", posted_date=old)
                yield RawJob(title="Fresh Role", company="A", url="https://x/fresh",
                             source="fake", posted_date=fresh)
                yield RawJob(title="Dateless Role", company="A",
                             url="https://x/nodate", source="fake")

        monkeypatch.setattr(pipeline, "_source_names", lambda: ["fake"])
        monkeypatch.setattr(pipeline, "_get_source", lambda name: FakeSource)
        monkeypatch.setattr(pipeline, "load_companies", lambda: [])
        pipeline.run_refresh("manual", force=True)
        jobs, _ = db.query_jobs(window=None, statuses=None, entry_level=None)
        urls = {j["url"] for j in jobs}
        assert urls == {"https://x/fresh", "https://x/nodate"}


class TestScrapedLiveness:
    def _seed(self, url, title):
        seed_board_job(url, source="jobspy", slug=None, title=title)

    def test_head_results_drive_delisting_honestly(self, tmp_db, monkeypatch):
        self._seed("https://indeed/dead", "Role Dead")
        self._seed("https://indeed/alive", "Role Alive")
        self._seed("https://indeed/error", "Role Err")
        self._seed("https://indeed/redirected", "Role Redir")
        before = job_by_url("https://indeed/alive")["last_seen_at"]

        def fake_head(url):
            if url.endswith("/dead"):
                return SimpleNamespace(status_code=404, url=url)
            if url.endswith("/alive"):
                return SimpleNamespace(status_code=200, url=url)
            if url.endswith("/redirected"):
                # bounced to the careers homepage: posting is gone
                return SimpleNamespace(status_code=200, url="https://indeed/")
            raise RuntimeError("network down")

        from engine.ingest import base

        monkeypatch.setattr(base, "polite_head", fake_head)
        pipeline._check_scraped_liveness(limit=10)
        assert job_by_url("https://indeed/dead")["delisted"] is True
        assert job_by_url("https://indeed/redirected")["delisted"] is True
        assert job_by_url("https://indeed/error")["delisted"] is False
        assert job_by_url("https://indeed/alive")["delisted"] is False
        assert job_by_url("https://indeed/alive")["last_seen_at"] > before


class TestBoardOkStamping:
    def test_greenhouse_marks_board_ok_only_after_full_yield(
        self, tmp_db, monkeypatch
    ):
        watchlist.add("greenhouse", "stripe", name="Stripe")
        from engine.ingest import greenhouse

        payload = {"jobs": [
            {"title": "SWE", "location": {"name": "SF"},
             "absolute_url": "https://gh/1", "content": "",
             "first_published": "2026-07-20"},
        ]}
        monkeypatch.setattr(
            greenhouse, "polite_get",
            lambda url, **kw: SimpleNamespace(json=lambda: payload),
        )
        gen = greenhouse.fetch_jobs(
            [{"name": "Stripe", "ats": "greenhouse", "slug": "stripe"}]
        )
        next(gen)
        rows = {r["slug"]: r for r in watchlist.list_all()}
        assert rows["stripe"]["last_ok_at"] is None  # jobs still streaming
        list(gen)  # consumer drains the board completely
        rows = {r["slug"]: r for r in watchlist.list_all()}
        assert rows["stripe"]["last_ok_at"]

    def test_greenhouse_failed_board_never_marked_ok(self, tmp_db, monkeypatch):
        watchlist.add("greenhouse", "stripe", name="Stripe")
        from engine.ingest import greenhouse

        def boom(url, **kw):
            raise RuntimeError("HTTP 404")

        monkeypatch.setattr(greenhouse, "polite_get", boom)
        list(greenhouse.fetch_jobs(
            [{"name": "Stripe", "ats": "greenhouse", "slug": "stripe"}]
        ))
        rows = {r["slug"]: r for r in watchlist.list_all()}
        assert rows["stripe"]["last_ok_at"] is None
