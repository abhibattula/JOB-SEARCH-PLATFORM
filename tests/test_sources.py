"""T008/T019-T021: source parsers against recorded fixtures + polite HTTP base."""
import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from engine.ingest import base

FIXTURES = Path(__file__).parent / "fixtures"


def load_fixture(name):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def fake_response(payload):
    return SimpleNamespace(json=lambda: payload, text=json.dumps(payload))


class TestPoliteHttp:
    def test_enforces_per_domain_gap(self, monkeypatch):
        sleeps = []
        clock = {"now": 1000.0}

        def fake_monotonic():
            return clock["now"]

        def fake_sleep(seconds):
            sleeps.append(seconds)
            clock["now"] += seconds

        monkeypatch.setattr(base.time, "monotonic", fake_monotonic)
        monkeypatch.setattr(base.time, "sleep", fake_sleep)
        base._LAST_REQUEST.clear()

        base._respect_rate_limit("boards-api.greenhouse.io")
        clock["now"] += 0.2  # 200ms later, same domain -> must wait ~0.8s
        base._respect_rate_limit("boards-api.greenhouse.io")
        base._respect_rate_limit("api.lever.co")  # other domain -> no wait

        assert len(sleeps) == 1
        assert sleeps[0] == pytest.approx(0.8, abs=0.05)

    def test_strip_html_unescapes_and_flattens(self):
        html = "&lt;p&gt;Build &amp;amp; ship&lt;/p&gt;"
        assert base.strip_html(html) == "Build & ship"
        assert base.strip_html("<div>Hello<br>world</div>") == "Hello world"


class TestGreenhouse:
    def test_parses_real_payload(self, monkeypatch):
        from engine.ingest import greenhouse

        monkeypatch.setattr(
            greenhouse, "polite_get",
            lambda url, **kw: fake_response(load_fixture("greenhouse_stripe.json")),
        )
        jobs = list(greenhouse.fetch_jobs([{"name": "Stripe", "slug": "stripe"}]))
        assert len(jobs) == 2
        first = jobs[0]
        assert first.title == "Account Executive, AI Sales (Grower)"
        assert first.company == "Stripe"
        assert first.url == "https://stripe.com/jobs/search?gh_jid=7954688"
        assert first.location == "San Francisco, CA"
        assert first.source == "greenhouse"
        assert first.posted_date == "2026-06-02"  # first_published, date part
        assert "About Stripe" in first.description
        assert "&lt;" not in first.description and "<p>" not in first.description


class TestLever:
    def test_parses_real_payload(self, monkeypatch):
        from engine.ingest import lever

        monkeypatch.setattr(
            lever, "polite_get",
            lambda url, **kw: fake_response(load_fixture("lever_palantir.json")),
        )
        jobs = list(lever.fetch_jobs([{"name": "Palantir", "slug": "palantir"}]))
        assert len(jobs) == 2
        first = jobs[0]
        assert first.title == "Administrative Business Partner"
        assert first.url.startswith("https://jobs.lever.co/palantir/")
        assert first.location == "London, United Kingdom"
        expected = datetime.fromtimestamp(1711403416463 / 1000, tz=timezone.utc)
        assert first.posted_date == expected.strftime("%Y-%m-%d")
        assert first.is_remote is False
        assert "World-Changing Company" in first.description


class TestAshby:
    def test_parses_real_payload(self, monkeypatch):
        from engine.ingest import ashby

        monkeypatch.setattr(
            ashby, "polite_get",
            lambda url, **kw: fake_response(load_fixture("ashby_openai.json")),
        )
        jobs = list(ashby.fetch_jobs([{"name": "OpenAI", "slug": "openai"}]))
        assert len(jobs) == 2
        first = jobs[0]
        assert first.title == "Technical Program Manager, Compute Infrastructure"
        assert first.url.startswith("https://jobs.ashbyhq.com/openai/")
        assert first.posted_date == "2026-03-12"
        assert first.location == "San Francisco"
        assert first.is_remote is False
        assert "compute infrastructure team" in first.description.lower()


class TestWorkday:
    def test_parses_cxs_payload_with_relative_dates(self, monkeypatch):
        from engine.ingest import workday

        monkeypatch.setattr(
            workday, "polite_post",
            lambda url, **kw: fake_response(load_fixture("workday_nvidia.json")),
        )
        entry = {
            "name": "NVIDIA",
            "host": "nvidia.wd5.myworkdayjobs.com",
            "site": "NVIDIAExternalCareerSite",
            "search": "engineer",
        }
        jobs = list(workday.fetch_jobs([entry]))
        assert len(jobs) == 3
        today = date.today()
        by_title = {j.title: j for j in jobs}
        assert by_title["ASIC Design Engineer, New College Grad"].posted_date == today.isoformat()
        assert (
            by_title["Hardware Engineer - GPU Verification"].posted_date
            == (today - timedelta(days=3)).isoformat()
        )
        assert (
            by_title["Senior Firmware Engineer"].posted_date
            == (today - timedelta(days=31)).isoformat()
        )
        url = by_title["ASIC Design Engineer, New College Grad"].url
        assert url.startswith(
            "https://nvidia.wd5.myworkdayjobs.com/en-US/NVIDIAExternalCareerSite/job/"
        )
        assert by_title["ASIC Design Engineer, New College Grad"].location == "US, CA, Santa Clara"


class TestHackerNews:
    def test_parses_pipe_comments_and_skips_rest(self, monkeypatch):
        from engine.ingest import hn

        search = load_fixture("hn_search.json")
        item = load_fixture("hn_item.json")

        def router(url, **kw):
            if "search_by_date" in url:
                return fake_response(search)
            return fake_response(item)

        monkeypatch.setattr(hn, "polite_get", router)
        jobs = list(hn.fetch_jobs([]))
        # fixture: 4 comments; only pipe-format ones become jobs
        assert 1 <= len(jobs) < 4
        flywheel = next(j for j in jobs if "Flywheel" in j.company)
        assert "Engineers" in flywheel.title
        assert flywheel.is_remote is True
        assert flywheel.posted_date == "2026-07-01"
        assert flywheel.url == "https://news.ycombinator.com/item?id=48747990"
        assert flywheel.source == "hn"
        # non-pipe comment (CaseLight prose) must be skipped
        assert not any("CaseLight" in j.company for j in jobs)


class TestSmartRecruiters:
    def test_parses_real_payload(self, monkeypatch):
        from engine.ingest import smartrecruiters

        monkeypatch.setattr(
            smartrecruiters, "polite_get",
            lambda url, **kw: fake_response(load_fixture("smartrecruiters_sample.json")),
        )
        jobs = list(smartrecruiters.fetch_jobs([{"name": "Visa", "slug": "Visa"}]))
        assert len(jobs) == 2
        first = jobs[0]
        assert first.title == "Sr. Manager"
        assert first.url == "https://jobs.smartrecruiters.com/Visa/744000133907678"
        assert first.location == "Austin, TX, United States"
        assert first.is_remote is False
        assert first.posted_date == "2026-06-24"
        assert "Mid-Senior Level" in first.description  # experience level feeds classifier
        assert first.source == "smartrecruiters"


class TestWorkable:
    def test_parses_real_payload(self, monkeypatch):
        from engine.ingest import workable

        monkeypatch.setattr(
            workable, "polite_post",
            lambda url, **kw: fake_response(load_fixture("workable_sample.json")),
        )
        jobs = list(workable.fetch_jobs([{"name": "Hugging Face", "slug": "huggingface"}]))
        assert len(jobs) >= 1
        first = jobs[0]
        assert "Python Software Engineer" in first.title
        assert first.url == "https://apply.workable.com/huggingface/j/F8427A442D/"
        assert first.is_remote is True
        assert first.posted_date == "2026-06-02"
        assert first.location == "United States"
        assert first.source == "workable"


class TestJobspy:
    def _frame(self):
        pd = pytest.importorskip("pandas")
        return pd.DataFrame(
            [
                {
                    "title": "Entry Level Hardware Engineer",
                    "company": "Micron",
                    "location": "Boise, ID",
                    "job_url": "https://www.indeed.com/viewjob?jk=abc123",
                    "date_posted": date.today() - timedelta(days=1),
                    "description": "Design memory subsystems.",
                    "is_remote": False,
                },
                {
                    "title": "New Grad Software Engineer",
                    "company": "NVIDIA",
                    "location": "Remote, US",
                    "job_url": "https://www.indeed.com/viewjob?jk=def456",
                    "date_posted": None,
                    "description": None,
                    "is_remote": True,
                },
            ]
        )

    def test_maps_dataframe_and_defaults_linkedin_off(self, monkeypatch):
        from engine.ingest import jobspy_source

        calls = []

        def fake_scrape(**kwargs):
            calls.append(kwargs)
            return self._frame()

        monkeypatch.setattr(jobspy_source, "_scrape", fake_scrape)
        monkeypatch.delenv("JOBSPY_LINKEDIN", raising=False)
        jobs = list(jobspy_source.fetch_jobs([]))

        assert all(set(c["site_name"]) == {"indeed"} for c in calls)
        assert len(jobs) >= 2
        first = next(j for j in jobs if j.company == "Micron")
        assert first.source == "jobspy"
        assert first.posted_date == (date.today() - timedelta(days=1)).isoformat()
        nvidia = next(j for j in jobs if j.company == "NVIDIA")
        assert nvidia.posted_date is None
        assert nvidia.is_remote is True
        assert nvidia.description == ""

    def test_linkedin_enabled_by_env(self, monkeypatch):
        from engine.ingest import jobspy_source

        calls = []

        def fake_scrape(**kwargs):
            calls.append(kwargs)
            return self._frame().head(0)

        monkeypatch.setattr(jobspy_source, "_scrape", fake_scrape)
        monkeypatch.setenv("JOBSPY_LINKEDIN", "1")
        list(jobspy_source.fetch_jobs([]))
        assert any("linkedin" in c["site_name"] for c in calls)
