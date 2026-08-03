"""021 US6 (FR-033): five more free, keyless, official JSON boards.

Same shape as greenhouse/lever/ashby, so they qualify as FULL_BOARD sources —
absence from a successful fetch authoritatively means the posting is gone,
which the delisting logic already depends on. They also reach the employer's
own careers page, so the apply URL is the genuine one rather than an
aggregator's copy.

Asserted against RECORDED responses, never the live network: a test that
needs the internet is a test that fails on a train.
"""
from __future__ import annotations

import pytest

from engine import pipeline, watchlist
from engine.ingest import SOURCE_ORDER, get_source

NEW = ("recruitee", "teamtailor", "personio", "breezy", "jazzhr")

RESPONSES: dict[str, dict] = {
    "recruitee": {
        "offers": [{
            "title": "RTL Design Engineer",
            "careers_url": "https://acme.recruitee.com/o/rtl-design-engineer",
            "city": "Austin", "country": "United States",
            "remote": False,
            "description": "<p>Verify <b>digital</b> designs.</p>",
            "published_at": "2026-07-30T09:00:00.000+02:00",
        }],
    },
    "teamtailor": {
        "jobs": [{
            "title": "RTL Design Engineer",
            "careersite-job-url": "https://acme.teamtailor.com/jobs/1-rtl",
            "location": "Austin, TX",
            "remote-status": "fully",
            "body": "<p>Verify <b>digital</b> designs.</p>",
            "created-at": "2026-07-30T09:00:00+02:00",
        }],
    },
    "personio": {
        "jobs": [{
            "id": 55, "name": "RTL Design Engineer",
            "url": "https://acme.jobs.personio.com/job/55",
            "office": "Austin, TX",
            "jobDescriptions": [{"value": "<p>Verify designs.</p>"}],
            "createdAt": "2026-07-30T09:00:00+02:00",
        }],
    },
    "breezy": {
        "positions": [{
            "id": "abc", "name": "RTL Design Engineer",
            "url": "https://acme.breezy.hr/p/abc",
            "location": {"city": "Austin",
                         "country": {"name": "United States"},
                         "is_remote": False},
            "description": "<p>Verify <b>digital</b> designs.</p>",
            "published_date": "2026-07-30T09:00:00Z",
        }],
    },
    "jazzhr": {
        "jobs": [{
            "board_code": "xyz", "title": "RTL Design Engineer",
            "city": "Austin", "state": "TX",
            "description": "<p>Verify <b>digital</b> designs.</p>",
            "original_open_date": "2026-07-30",
        }],
    },
}


class _Response:
    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload


@pytest.fixture()
def entries():
    return [{"slug": "acme", "name": "Acme Semiconductors"}]


class TestEachNewBoardParses:
    @pytest.mark.parametrize("name", NEW)
    def test_a_recorded_response_yields_a_usable_job(self, name, entries,
                                                     monkeypatch):
        module = get_source(name)
        monkeypatch.setattr(
            module, "polite_get",
            lambda url, **kw: _Response(RESPONSES[name]))
        jobs = list(module.fetch_jobs(entries))

        assert len(jobs) == 1
        job = jobs[0]
        assert job.title == "RTL Design Engineer"
        assert job.company == "Acme Semiconductors"
        assert job.url.startswith("https://")
        assert job.source == name
        assert job.company_ats_type == name
        assert job.company_ats_slug == "acme"

    @pytest.mark.parametrize("name", NEW)
    def test_the_posted_date_is_an_iso_day(self, name, entries, monkeypatch):
        """Recency is a first-class requirement (Constitution): a job with a
        malformed date is silently dropped at ingest."""
        module = get_source(name)
        monkeypatch.setattr(
            module, "polite_get",
            lambda url, **kw: _Response(RESPONSES[name]))
        posted = list(module.fetch_jobs(entries))[0].posted_date
        assert posted == "2026-07-30"

    @pytest.mark.parametrize("name", NEW)
    def test_html_is_stripped_from_the_description(self, name, entries,
                                                   monkeypatch):
        module = get_source(name)
        monkeypatch.setattr(
            module, "polite_get",
            lambda url, **kw: _Response(RESPONSES[name]))
        description = list(module.fetch_jobs(entries))[0].description
        assert "<" not in description
        assert "Verify" in description

    @pytest.mark.parametrize("name", NEW)
    def test_a_failing_board_yields_nothing_and_does_not_raise(
            self, name, entries, monkeypatch):
        module = get_source(name)

        def boom(*a, **k):
            raise OSError("network down")

        monkeypatch.setattr(module, "polite_get", boom)
        assert list(module.fetch_jobs(entries)) == []

    @pytest.mark.parametrize("name", NEW)
    def test_one_bad_board_does_not_stop_the_next(self, name, monkeypatch):
        """FR-033 / Constitution III: a failure in one source must not abort
        the others — and that applies within a source too."""
        module = get_source(name)
        calls = {"n": 0}

        def flaky(url, **kw):
            calls["n"] += 1
            if calls["n"] == 1:
                raise OSError("first board is down")
            return _Response(RESPONSES[name])

        monkeypatch.setattr(module, "polite_get", flaky)
        jobs = list(module.fetch_jobs([
            {"slug": "broken", "name": "Broken Co"},
            {"slug": "acme", "name": "Acme Semiconductors"},
        ]))
        assert len(jobs) == 1
        assert jobs[0].company == "Acme Semiconductors"

    @pytest.mark.parametrize("name", NEW)
    def test_an_empty_board_is_not_an_error(self, name, entries, monkeypatch):
        module = get_source(name)
        monkeypatch.setattr(module, "polite_get",
                            lambda url, **kw: _Response({}))
        assert list(module.fetch_jobs(entries)) == []


class TestTheyAreWiredIn:
    @pytest.mark.parametrize("name", NEW)
    def test_the_registry_knows_it(self, name):
        assert name in SOURCE_ORDER
        assert get_source(name).SOURCE_NAME == name

    @pytest.mark.parametrize("name", NEW)
    def test_it_counts_as_a_full_board(self, name):
        """Which is what authorises board-diff delisting for it."""
        assert name in pipeline.FULL_BOARD_SOURCES

    @pytest.mark.parametrize("name", NEW)
    def test_a_company_can_be_watchlisted_for_it(self, name):
        assert name in watchlist.VALID_ATS

    @pytest.mark.parametrize("name", NEW)
    def test_it_authorises_delisting_only_after_yielding(self, name, entries,
                                                         monkeypatch):
        """`board_ok` must be called AFTER the jobs are yielded — an
        abandoned generator must not qualify its board for delisting, or a
        partial fetch would mark every other posting dead."""
        module = get_source(name)
        monkeypatch.setattr(module, "polite_get",
                            lambda url, **kw: _Response(RESPONSES[name]))
        seen = []
        monkeypatch.setattr(module, "board_ok",
                            lambda source, slug: seen.append(slug))

        generator = module.fetch_jobs(entries)
        next(generator)                      # first job out, board NOT ok yet
        assert seen == []
        list(generator)                      # drain
        assert seen == ["acme"]


class TestTheyStayPolite:
    """Constitution III: at most one request per second per domain, an honest
    User-Agent, no bot-protection bypass."""

    @pytest.mark.parametrize("name", NEW)
    def test_every_request_goes_through_the_rate_limiter(self, name):
        source = (get_source(name).__file__)
        text = open(source, encoding="utf-8").read()
        assert "polite_get" in text or "polite_post" in text
        # A raw client would bypass the process-wide per-domain limiter.
        for forbidden in ("httpx.get", "httpx.Client(", "requests.get",
                          "urllib.request"):
            assert forbidden not in text, f"{name} bypasses base.py: {forbidden}"

    @pytest.mark.parametrize("name", NEW)
    def test_it_sends_no_credentials(self, name):
        """These are public endpoints. Anything sending an Authorization
        header would mean this is not the free, keyless source it claims."""
        text = open(get_source(name).__file__, encoding="utf-8").read()
        for forbidden in ("Authorization", "api_key", "apikey", "Bearer"):
            assert forbidden not in text, name
