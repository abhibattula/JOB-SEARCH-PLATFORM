"""022 (F-A) — the dashboard stops eating the screen.

Measuring the v2.1.0 baseline turned up something no test would have caught:
roughly 695px of a 768px viewport was chrome before the first job. The
dashboard's three full-height cards were ~315px of it, which is why the feed
showed six jobs on a standard laptop.

The information is worth keeping — it is the home screen's whole reason to
exist. The three tall cards are not. This makes it one strip, and lets the
applicant hide it entirely.
"""
from __future__ import annotations

import json
import re

import pytest
from fastapi.testclient import TestClient

from engine import db, settings

HOME = "/?window=all&sort=score&entry_level=all"


@pytest.fixture()
def client(tmp_db, monkeypatch):
    monkeypatch.setenv("REFRESH_SYNC", "1")
    from engine import matcher, pipeline

    monkeypatch.setattr(pipeline, "_source_names", lambda: [])
    monkeypatch.setattr(pipeline, "load_companies", lambda: [])
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.setattr(matcher.local_llm, "available", lambda: False)
    from web.main import create_app

    return TestClient(create_app())


def _seed(n=1, score=81, method="llm"):
    db.upsert_job({
        "title": f"Embedded Engineer {n}", "company": f"Aurora {n}",
        "url": f"https://example.test/j/{n}", "source": "greenhouse",
        "location": "Hillsboro, OR", "is_remote": False,
        "description": "v", "posted_date": "2026-08-01"})
    job_id = [r["id"] for r in db.list_all_jobs_minimal()][-1]
    db.set_match(job_id, score, json.dumps(
        {"match_score": score, "method": method, "matching_skills": [],
         "missing_skills": [], "reasoning": "x"}))
    return job_id


class TestNothingWasLost:
    """A smaller dashboard that drops information is not smaller, it is worse."""

    def test_top_matches_are_still_shown(self, client):
        _seed(1)
        body = client.get(HOME).text
        assert "Embedded Engineer 1" in body

    def test_a_top_match_still_shows_its_provenance(self, client):
        """The stamp goes wherever a score goes (FR-018) — including here."""
        _seed(1, method="basic")
        body = client.get(HOME).text
        strip = re.search(r'<section class="dashboard".*?</section>', body,
                          re.S)
        assert strip, "the dashboard is gone entirely"
        assert "stamp--pencil" in strip.group(0)

    def test_application_counts_are_still_shown(self, client):
        body = client.get(HOME).text
        strip = re.search(r'<section class="dashboard".*?</section>', body,
                          re.S).group(0)
        for word in ("applied", "interviewing", "saved"):
            assert word in strip

    def test_next_actions_are_still_reachable(self, client):
        body = client.get(HOME).text
        assert "next-actions" in body


class TestItCanBeHidden:
    def test_it_is_shown_by_default(self, client):
        assert 'class="dashboard"' in client.get(HOME).text

    def test_hiding_it_persists(self, client):
        settings.set("DASHBOARD_HIDDEN", "1")
        body = client.get(HOME).text
        assert 'class="dashboard"' not in body, (
            "the dashboard should be gone when hidden")
        assert "dash-show" in body, (
            "…but there must be a way back — hiding it must not be a one-way "
            "door")

    def test_there_is_a_control_to_hide_it(self, client):
        assert "dash-hide" in client.get(HOME).text


class TestItIsAStripNotAWall:
    def test_the_three_cards_are_gone(self, client):
        body = client.get(HOME).text
        assert "dash-grid" not in body, (
            "the three-card grid was ~315px of a 768px viewport")

    def test_the_strip_is_one_row(self):
        from pathlib import Path
        css = (Path(__file__).resolve().parents[1] / "web" / "static"
               / "styles.css").read_text(encoding="utf-8")
        block = re.search(r"\.dash-strip\s*\{([^}]*)\}", css)
        assert block, ".dash-strip is not defined"
        assert "flex" in block.group(1) or "grid" in block.group(1)
