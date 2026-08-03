"""022 US3 — the feed stays still while it is being read.

Before this feature `feed.html` polled every 5 seconds with
`hx-swap="innerHTML"` over the whole `#feed-region`, unconditionally. Reading
the feed for one minute destroyed and rebuilt the table twelve times, losing
scroll position, hover state and any in-flight transition each time. It is the
largest single contributor to the app feeling unfinished in motion, and it is
a server problem, not an animation problem.

The fix is to stop sending HTML that changes nothing: the server fingerprints
what it is about to render, and answers 204 when the client already has it.
htmx performs no swap on a 204, so the DOM is untouched.

Contract: specs/022-the-case-file/data-model.md section 4.
"""
from __future__ import annotations

import json
import re

import pytest
from fastapi.testclient import TestClient

from engine import db

FEED = "/partials/feed?window=all&sort=score&entry_level=all"


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


def _seed(n: int = 1, **over) -> int:
    db.upsert_job({
        "title": over.pop("title", "Embedded Software Engineer"),
        "company": f"Aurora Semiconductors {n}",
        "url": f"https://example.test/job/{n}",
        "source": "greenhouse",
        "location": "Hillsboro, OR",
        "is_remote": False,
        "description": "verilog uvm",
        "posted_date": "2026-08-01",
        **over,
    })
    return [r["id"] for r in db.list_all_jobs_minimal()][-1]


def _fingerprint_of(body: str) -> str:
    match = re.search(r'data-fp="([^"]+)"', body)
    assert match, "the feed partial must publish its fingerprint"
    return match.group(1)


class TestTheFeedGoesQuiet:
    def test_first_request_returns_the_table(self, client):
        _seed()
        resp = client.get(FEED)
        assert resp.status_code == 200
        assert "score-cell" in resp.text

    def test_an_unchanged_repeat_returns_204_and_no_body(self, client):
        _seed()
        first = client.get(FEED)
        fp = _fingerprint_of(first.text)
        again = client.get(FEED, headers={"X-Feed-Fingerprint": fp})
        assert again.status_code == 204, (
            "the feed re-sent an identical table; htmx will swap it and the "
            "applicant loses scroll and hover")
        assert not again.content

    def test_a_real_change_still_arrives(self, client):
        """FR-028 — going quiet must not mean going deaf."""
        job_id = _seed()
        fp = _fingerprint_of(client.get(FEED).text)
        db.set_status(job_id, "saved")
        changed = client.get(FEED, headers={"X-Feed-Fingerprint": fp})
        assert changed.status_code == 200
        assert _fingerprint_of(changed.text) != fp

    def test_a_new_job_still_arrives(self, client):
        _seed(1)
        fp = _fingerprint_of(client.get(FEED).text)
        _seed(2)
        assert client.get(
            FEED, headers={"X-Feed-Fingerprint": fp}).status_code == 200

    def test_an_unknown_fingerprint_is_served_normally(self, client):
        """A stale or hand-made value must never wedge the feed shut."""
        _seed()
        resp = client.get(FEED, headers={"X-Feed-Fingerprint": "nonsense"})
        assert resp.status_code == 200


class TestTheFingerprintCoversWhatIsVisible:
    """data-model.md section 4 — everything the applicant can see is hashed;
    nothing they cannot is."""

    def _fp_after(self, client, mutate) -> tuple[str, str]:
        job_id = _seed()
        before = _fingerprint_of(client.get(FEED).text)
        mutate(job_id)
        after = _fingerprint_of(client.get(FEED).text)
        return before, after

    def test_a_score_change_changes_it(self, client):
        before, after = self._fp_after(client, lambda jid: db.set_match(
            jid, 81, json.dumps({"match_score": 81, "method": "llm",
                                 "matching_skills": [], "missing_skills": [],
                                 "reasoning": "x"})))
        assert before != after

    def test_a_method_change_alone_changes_it(self, client):
        """The number can stay identical while the stamp changes from a
        pencil guess to a sealed analysis. That is a visible change."""
        job_id = _seed()
        db.set_match(job_id, 72, json.dumps(
            {"match_score": 72, "method": "basic", "matching_skills": [],
             "missing_skills": [], "reasoning": "x"}))
        before = _fingerprint_of(client.get(FEED).text)
        db.set_match(job_id, 72, json.dumps(
            {"match_score": 72, "method": "llm", "matching_skills": [],
             "missing_skills": [], "reasoning": "x"}))
        after = _fingerprint_of(client.get(FEED).text)
        assert before != after, (
            "same score, different provenance — the stamp changes, so the "
            "fingerprint must too")

    def test_a_note_edit_changes_it(self, client):
        """A presence-only flag would be wrong here: editing a note from
        'call back' to 'sent email' changes the visible summary while
        presence stays true, and the row would never refresh."""
        job_id = _seed()
        db.set_status(job_id, "applied")
        db.set_notes(job_id, "call back")
        before = _fingerprint_of(client.get(
            "/partials/feed?window=all&status=applied&entry_level=all").text)
        db.set_notes(job_id, "sent email")
        after = _fingerprint_of(client.get(
            "/partials/feed?window=all&status=applied&entry_level=all").text)
        assert before != after

    def test_identical_data_gives_an_identical_fingerprint(self, client):
        _seed()
        assert (_fingerprint_of(client.get(FEED).text)
                == _fingerprint_of(client.get(FEED).text))

    def test_a_different_query_gives_a_different_fingerprint(self, client):
        """Two views must never collide, or switching filters would 204."""
        _seed()
        a = _fingerprint_of(client.get(FEED).text)
        b = _fingerprint_of(client.get(
            "/partials/feed?window=all&sort=date&entry_level=all").text)
        assert a != b
