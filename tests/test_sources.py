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


class TestSimplify:
    def test_parses_active_listings_and_maps_sponsorship(self, monkeypatch):
        from engine.ingest import simplify

        payload = load_fixture("simplify_listings.json") + [
            {
                "title": "Old Role", "company_name": "Gone Inc",
                "url": "https://x.example/old", "active": False,
                "is_visible": True, "locations": [], "date_posted": 1700000000,
                "sponsorship": "Other",
            },
            {
                "title": "Citizens Role", "company_name": "Defense Co",
                "url": "https://x.example/cit", "active": True,
                "is_visible": True, "locations": ["Remote in USA"],
                "date_posted": 1783000000,
                "sponsorship": "U.S. Citizenship is Required",
            },
        ]
        monkeypatch.setattr(simplify, "polite_get", lambda url, **kw: fake_response(payload))
        jobs = list(simplify.fetch_jobs([]))

        assert not any(j.title == "Old Role" for j in jobs)  # inactive skipped
        first = jobs[0]
        assert first.source == "simplify"
        assert first.company == "RWS"
        expected_date = datetime.fromtimestamp(1763766945, tz=timezone.utc).strftime("%Y-%m-%d")
        assert first.posted_date == expected_date

        citizens = next(j for j in jobs if j.title == "Citizens Role")
        assert citizens.is_remote is True
        assert "U.S. Citizenship is Required" in citizens.description

    def test_sponsorship_field_drives_scanner(self):
        from engine import filters

        flag, phrase = filters.scan_sponsorship("Sponsorship: U.S. Citizenship is Required.")
        assert flag == -1
        flag, _ = filters.scan_sponsorship("Sponsorship: Offers Sponsorship.")
        assert flag == 1
        flag, _ = filters.scan_sponsorship("Sponsorship: Does Not Offer Sponsorship.")
        assert flag == -1
        flag, _ = filters.scan_sponsorship("Sponsorship: Other.")
        assert flag == 0


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

        # 008: google joined the default site list; linkedin stays opt-in
        assert all(set(c["site_name"]) == {"indeed", "google"} for c in calls)
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


class TestJobspy008:
    """008 US3 (T031/T042): settings-driven sites/volume, 14-day hours_old
    passed ALONE (mutual-exclusivity), and profile-driven terms/locations."""

    def _capture(self, monkeypatch):
        from engine.ingest import jobspy_source

        calls = []

        def fake_scrape(**kw):
            calls.append(kw)
            return None

        monkeypatch.setattr(jobspy_source, "_scrape", fake_scrape)
        return calls

    def test_default_sites_are_indeed_and_google(self, tmp_db, monkeypatch):
        from engine.ingest import jobspy_source

        calls = self._capture(monkeypatch)
        list(jobspy_source.fetch_jobs([]))
        assert calls and calls[0]["site_name"] == ["indeed", "google"]

    def test_linkedin_appended_only_when_opted_in(self, tmp_db, monkeypatch):
        from engine import db as edb
        from engine.ingest import jobspy_source

        edb.set_setting("JOBSPY_LINKEDIN", "1")
        calls = self._capture(monkeypatch)
        list(jobspy_source.fetch_jobs([]))
        assert calls[0]["site_name"] == ["indeed", "google", "linkedin"]

    def test_hours_old_is_336_and_passed_alone(self, tmp_db, monkeypatch):
        from engine.ingest import jobspy_source

        calls = self._capture(monkeypatch)
        list(jobspy_source.fetch_jobs([]))
        kw = calls[0]
        assert kw["hours_old"] == 336
        # jobspy treats hours_old as mutually exclusive with these — none
        # may ever be passed alongside it (client-side filtering only)
        assert not {"job_type", "is_remote", "easy_apply"} & set(kw)

    def test_results_wanted_from_settings(self, tmp_db, monkeypatch):
        from engine import db as edb
        from engine.ingest import jobspy_source

        edb.set_setting("JOBSPY_RESULTS_PER_SEARCH", "60")
        calls = self._capture(monkeypatch)
        list(jobspy_source.fetch_jobs([]))
        assert calls[0]["results_wanted"] == 60

    def test_profile_terms_and_locations_drive_searches(self, tmp_db, monkeypatch):
        from engine import db as edb
        from engine.ingest import jobspy_source

        edb.save_profile(
            search_terms={"terms": ["fpga engineer", "asic verification"]},
            target_locations=["Austin, TX"],
        )
        calls = self._capture(monkeypatch)
        list(jobspy_source.fetch_jobs([]))
        combos = {(c["search_term"], c["location"]) for c in calls}
        assert combos == {
            ("fpga engineer", "Austin, TX"),
            ("asic verification", "Austin, TX"),
        }

    def test_empty_profile_falls_back_to_builtin_terms(self, tmp_db, monkeypatch):
        from engine.ingest import jobspy_source

        calls = self._capture(monkeypatch)
        list(jobspy_source.fetch_jobs([]))
        assert len(calls) == len(jobspy_source.SEARCH_TERMS)
        assert all(c["location"] == "United States" for c in calls)

    def test_total_searches_capped(self, tmp_db, monkeypatch):
        from engine import db as edb
        from engine.ingest import jobspy_source

        edb.save_profile(
            search_terms={"terms": [f"term {i}" for i in range(6)]},
            target_locations=["Austin, TX", "San Jose, CA", "Remote"],
        )
        calls = self._capture(monkeypatch)
        list(jobspy_source.fetch_jobs([]))
        assert len(calls) <= jobspy_source.MAX_SEARCHES_PER_RUN


class TestLinkedInLinkout:
    """008 US3 (T032): honest LinkedIn reach — one-click search link-outs
    (14-day filter) instead of default-on scraping that silently 429s."""

    def test_search_url_encodes_terms_and_fortnight_filter(self):
        from engine.ingest import linkedin_linkout

        url = linkedin_linkout.search_url("fpga engineer", location="Austin, TX")
        assert url.startswith("https://www.linkedin.com/jobs/search/?")
        assert "keywords=fpga+engineer" in url
        assert "f_TPR=r1209600" in url  # posted within 14 days
        assert "location=Austin%2C+TX" in url

    def test_url_for_job_uses_title(self):
        from engine.ingest import linkedin_linkout

        url = linkedin_linkout.url_for_job({"title": "Design Verification Engineer"})
        assert "keywords=Design+Verification+Engineer" in url
