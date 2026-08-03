"""022 (FR-026/026a/026b) — density, without losing scanning throughput.

The approved preview implied a roomy record card. Clarification settled it the
other way: compact stays the default and stays ONE LINE per job, because the
applicant works through hundreds of postings and a card layout would cut what
fits on screen from ~28 rows to ~8. Comfortable is available on demand.

SC-012 is the guard: the default density must show at least as many jobs per
screen as v2.1.0 did. The measured baseline is 6 (baseline.txt).
"""
from __future__ import annotations

import re

import pytest
from fastapi.testclient import TestClient

from engine import db, settings

FEED = "/?window=all&sort=score&entry_level=all"


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


def _seed(n=1):
    db.upsert_job({
        "title": "Embedded Software Engineer",
        "company": f"Aurora {n}", "url": f"https://example.test/j/{n}",
        "source": "greenhouse", "location": "Hillsboro, OR",
        "is_remote": False, "description": "v", "posted_date": "2026-08-01"})


def _density(body: str) -> str | None:
    match = re.search(r'data-density="([^"]+)"', body)
    return match.group(1) if match else None


class TestDensity:
    def test_compact_is_the_default(self, client):
        """FR-026a — scanning throughput is the applicant's primary need."""
        _seed()
        assert _density(client.get(FEED).text) == "compact"

    def test_the_choice_is_honoured(self, client):
        _seed()
        settings.set("FEED_DENSITY", "comfortable")
        assert _density(client.get(FEED).text) == "comfortable"

    def test_the_choice_persists(self, client):
        """FR-026 — across restarts, which means it lives in the store, not
        in a cookie or in memory."""
        settings.set("FEED_DENSITY", "comfortable")
        assert settings.get("FEED_DENSITY") == "comfortable"

    def test_a_nonsense_value_falls_back_to_compact(self, client):
        _seed()
        settings.set("FEED_DENSITY", "enormous")
        assert _density(client.get(FEED).text) == "compact"

    def test_both_densities_show_the_same_jobs(self, client):
        """FR-026b — density changes presentation, never which jobs appear.
        A density that filtered would be a bug disguised as a preference."""
        for n in range(3):
            _seed(n)
        compact = client.get("/partials/feed?window=all&entry_level=all").text
        settings.set("FEED_DENSITY", "comfortable")
        roomy = client.get("/partials/feed?window=all&entry_level=all").text
        assert compact.count("score-cell") == roomy.count("score-cell") == 3

    def test_one_row_element_per_job_at_compact(self, client):
        """FR-026a — one line per job. Two <tr> per job would halve what
        fits on screen without anyone noticing in a diff."""
        for n in range(4):
            _seed(n)
        body = client.get("/partials/feed?window=all&entry_level=all").text
        table = re.search(r"<tbody>(.*?)</tbody>", body, re.S)
        assert table, "no feed table body"
        assert len(re.findall(r"<tr\b", table.group(1))) == 4


class TestDensityIsCssNotMarkup:
    def test_one_template_serves_both(self):
        """Two templates would drift. The whole difference must be CSS
        keyed off data-density."""
        from pathlib import Path
        css = (Path(__file__).resolve().parents[1] / "web" / "static"
               / "styles.css").read_text(encoding="utf-8")
        assert 'data-density="comfortable"' in css, (
            "comfortable density must be expressed in CSS")
