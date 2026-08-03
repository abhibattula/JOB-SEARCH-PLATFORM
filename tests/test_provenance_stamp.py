"""022 US2 — a score never hides how it was produced.

The applicant decides which jobs are worth an hour of their evening from this
number. Before this feature its provenance was a single `~` or `•` character
plus a `title` tooltip, which is invisible in normal use: a keyword guess and
a full AI analysis looked the same at a glance.

The stored values were verified in research R2 and are NOT what the tier
function returns — `scoring_tier()` says "cloud" but `upgrade.py:288` stores
`"llm"`. Reading the tier name into a template would render a stamp that never
appears, which is precisely the class of bug this file exists to prevent.

Contract: specs/022-the-case-file/contracts/provenance-stamp.md (S1-S5).
"""
from __future__ import annotations

import json
import re

import pytest
from fastapi.testclient import TestClient

from engine import db

# value -> (ring style that must appear, phrase that must be readable)
PROVENANCE = {
    "basic": ("pencil", "keyword match"),
    "local": ("ink", "scored on this computer"),
    "llm": ("sealed", "full analysis"),
}


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


def _seed(method: str | None, score: float | None = 72, n: int = 1) -> int:
    db.upsert_job({
        "title": "Embedded Software Engineer",
        "company": f"Aurora Semiconductors {n}",
        "url": f"https://example.test/job/{n}",
        "source": "greenhouse",
        "location": "Hillsboro, OR",
        "is_remote": False,
        "description": "verilog systemverilog uvm",
        "posted_date": "2026-08-01",
    })
    job_id = [r["id"] for r in db.list_all_jobs_minimal()][-1]
    if method is not None:
        db.set_match(job_id, score, json.dumps({
            "match_score": score, "method": method,
            "matching_skills": [], "missing_skills": [],
            "reasoning": "seeded"}))
    return job_id


# The feed table and the home page are DIFFERENT surfaces. Asserting against
# the whole home page proves nothing about the table: the dashboard's "Top
# matches" also renders stamps, and it queries with entry_level=None while the
# table defaults to entry-level-only. An unclassified job therefore appears in
# the dashboard and not in the table — so a whole-page assertion passes even
# when the table's stamp is broken. It did, while this was being written.
#
# `/partials/feed` renders the table alone. Every table assertion uses it.
FEED_TABLE = "/partials/feed?window=all&sort=score&entry_level=all"


class TestStampRendersProvenance:
    """S1/S2 — each value renders a distinct treatment plus readable text."""

    @pytest.mark.parametrize("method", sorted(PROVENANCE))
    def test_feed_table_shows_the_treatment_and_the_phrase(self, client,
                                                           method):
        _seed(method)
        body = client.get(FEED_TABLE).text
        assert "score-cell" in body, "the feed table rendered no job rows"
        ring, phrase = PROVENANCE[method]
        assert f"stamp--{ring}" in body, (
            f"method {method!r} should render the {ring} stamp")
        assert phrase in body, (
            f"method {method!r} must state its provenance as text, not "
            f"colour alone (FR-017)")

    @pytest.mark.parametrize("method", sorted(PROVENANCE))
    def test_dashboard_agrees_with_the_table(self, client, method):
        """FR-018 — the same job must not read differently on two surfaces."""
        _seed(method)
        home = client.get("/?window=all&sort=score").text
        ring, _ = PROVENANCE[method]
        assert f"stamp--{ring}" in home, (
            "the dashboard's top-match stamp disagrees with the feed. "
            "match_method has to travel into the dashboard projection.")

    @pytest.mark.parametrize("method", sorted(PROVENANCE))
    def test_job_page_shows_the_same_treatment(self, client, method):
        job_id = _seed(method)
        body = client.get(f"/jobs/{job_id}").text
        ring, phrase = PROVENANCE[method]
        assert f"stamp--{ring}" in body
        assert phrase in body

    def test_the_three_treatments_are_actually_different(self, client):
        """S1 — a stamp that renders identically for every value tells the
        applicant nothing. This is the assertion that would catch someone
        wiring all three to the same class."""
        rings = {PROVENANCE[m][0] for m in PROVENANCE}
        assert len(rings) == 3, "each provenance needs its own treatment"


class TestUnscoredIsExplicit:
    """S4 — absence is a state, not a blank."""

    def test_a_job_with_no_match_row_says_so(self, client):
        _seed(None)
        body = client.get(FEED_TABLE).text
        assert "score-cell" in body, "the feed table rendered no job rows"
        assert "stamp--unscored" in body
        assert "not scored yet" in body


class TestColourIsNeverTheOnlySignal:
    """S1/FR-016 — the stamp must survive greyscale and colour-blindness."""

    def test_each_treatment_carries_a_non_colour_differentiator(self):
        from pathlib import Path
        css = (Path(__file__).resolve().parents[1] / "web" / "static"
               / "styles.css").read_text(encoding="utf-8")
        for ring in ("pencil", "ink", "sealed", "unscored"):
            block = re.search(r"\.stamp--" + ring + r"\b[^{]*\{([^}]*)\}", css)
            assert block, f".stamp--{ring} is not defined"
            body = block.group(1)
            assert ("border-style" in body or "border" in body
                    or "outline" in body or "box-shadow" in body), (
                f".stamp--{ring} differs only by colour; it needs a ring "
                f"style too (FR-016)")


class TestTheExplanationSurvives:
    """S5 — the tooltip told the applicant what to DO about a basic score.
    The stamp adds a signal; it must not remove an instruction."""

    def test_basic_still_explains_how_to_improve_it(self, client):
        _seed("basic")
        body = client.get(FEED_TABLE).text
        assert "AI key in Settings" in body


class TestStoredValuesNotTierNames:
    """R2 — the guard against the bug this feature nearly shipped."""

    def test_the_template_never_keys_on_the_word_cloud(self):
        from pathlib import Path
        root = Path(__file__).resolve().parents[1] / "web" / "templates"
        for path in root.rglob("*.html"):
            text = path.read_text(encoding="utf-8", errors="replace")
            assert not re.search(r"match_method\s*==\s*['\"]cloud['\"]", text), (
                f"{path.name} keys the stamp on 'cloud'. scoring_tier() "
                f"returns that, but upgrade.py:288 STORES 'llm' — this "
                f"stamp would never render.")
