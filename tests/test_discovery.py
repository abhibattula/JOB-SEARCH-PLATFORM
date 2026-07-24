"""012 (Discovery Copilot): on-demand scoring + sponsorship service.

Pure-engine unit tests — no browser, no bridge. Covers db.get_job_by_url,
the sponsorship.grade_company refactor (parity with apply_to_companies), and
discovery.score_page (match, two-tier sponsorship, no-resume, already_saved,
band cutoffs).
"""
import pytest

from engine import basic_match, db, discovery, sponsorship


# --- db.get_job_by_url -------------------------------------------------------

def test_get_job_by_url(tmp_db):
    db.upsert_job({
        "title": "New Grad SWE", "company": "Aurora Semiconductors",
        "url": "https://jobs.example.com/aurora/1", "source": "manual",
        "location": "Austin, TX", "description": "python verilog", "posted_date": None,
    })
    hit = db.get_job_by_url("https://jobs.example.com/aurora/1")
    assert hit is not None
    assert hit["title"] == "New Grad SWE"
    assert "id" in hit
    assert db.get_job_by_url("https://jobs.example.com/nope") is None


# --- sponsorship.grade_company (refactor, parity) ----------------------------

def _seed_employer(name, approvals, denials=0):
    db.store_h1b_employers({
        db.normalize_company(name): {
            "display_name": name, "approvals": approvals, "denials": denials,
            "wage_level_median": None, "wage_offered_median": None, "lca_titles": None,
        }
    })


def test_grade_company_matches_direct_grade(tmp_db):
    _seed_employer("Aurora Semiconductors", approvals=500, denials=20)
    result = sponsorship.grade_company("Aurora Semiconductors")
    expected = sponsorship.grade(500, 20)
    assert result["sponsor_grade"] == expected
    assert result["approvals"] == 500
    assert result["has_sponsor_data"] is True
    assert result["cap_exempt"] is False


def test_grade_company_unknown_is_honest(tmp_db):
    result = sponsorship.grade_company("Totally Unknown LLC")
    assert result["sponsor_grade"] is None
    assert result["has_sponsor_data"] is False


def test_grade_company_cap_exempt_flag(tmp_db):
    result = sponsorship.grade_company("Stanford University")
    assert result["cap_exempt"] is True


def test_grade_company_parity_with_apply_to_companies(tmp_db):
    """grade_company must produce the same grade the batch pass writes."""
    _seed_employer("Palantir Technologies", approvals=300, denials=10)
    db.upsert_job({
        "title": "SWE", "company": "Palantir Technologies",
        "url": "https://x/pltr/1", "source": "greenhouse",
        "location": "NYC", "description": "d", "posted_date": None,
    })
    sponsorship.apply_to_companies()
    batch = db.get_company_by_name("Palantir Technologies")
    on_demand = sponsorship.grade_company("Palantir Technologies")
    assert on_demand["sponsor_grade"] == batch["sponsor_grade"]
    assert on_demand["approvals"] == batch["h1b_approvals"]


# --- discovery.score_page ----------------------------------------------------

def _seed_profile(resume="python verilog fpga rtl", skills=None):
    db.save_profile(
        first_name="Abhinav", last_name="B", email="a@b.com",
        resume_text=resume, skills=skills or [],
    )


def test_score_page_computes_match(tmp_db):
    _seed_profile()
    result = discovery.score_page(
        "FPGA Design Engineer", "Aurora Semiconductors",
        "Seeking python verilog fpga experience", url="https://x/1",
    )
    reference = basic_match.score("python verilog fpga rtl",
                                  "FPGA Design Engineer",
                                  "Seeking python verilog fpga experience",
                                  extra_skills=set())
    assert result["match_score"] == reference.match_score
    assert result["needs_resume"] is False
    assert result["band"] in ("strong", "good", "fair")


def test_score_page_no_resume_is_honest(tmp_db):
    # profile exists but no resume_text
    db.save_profile(first_name="A", last_name="B", email="a@b.com")
    result = discovery.score_page("SWE", "Acme", "python", url="https://x/2")
    assert result["needs_resume"] is True
    assert result["match_score"] is None
    assert result["band"] == "none"


def test_score_page_sponsor_fast_path(tmp_db):
    _seed_profile()
    db.upsert_job({
        "title": "SWE", "company": "GradedCo", "url": "https://x/gc/1",
        "source": "greenhouse", "location": "SF", "description": "d",
        "posted_date": None,
    })
    company = db.get_company_by_name("GradedCo")
    db.set_company_sponsorship(company["id"], approvals=250,
                               sponsor_score="HIGH", sponsor_grade="B")
    result = discovery.score_page("SWE", "GradedCo", "python", url="https://x/q")
    assert result["sponsor_grade"] == "B"
    assert result["has_sponsor_data"] is True


def test_score_page_sponsor_on_demand_when_not_in_feed(tmp_db):
    _seed_profile()
    _seed_employer("Nebula Robotics", approvals=400, denials=15)
    # company has no jobs row → get_company_by_name miss → on-demand path
    result = discovery.score_page("SWE", "Nebula Robotics", "python", url="https://x/3")
    assert result["sponsor_grade"] == sponsorship.grade(400, 15)
    assert result["has_sponsor_data"] is True


def test_score_page_sponsor_unknown_never_fabricated(tmp_db):
    _seed_profile()
    result = discovery.score_page("SWE", "Nobody Inc", "python", url="https://x/4")
    assert result["sponsor_grade"] is None
    assert result["has_sponsor_data"] is False


def test_score_page_already_saved(tmp_db):
    _seed_profile()
    db.upsert_job({
        "title": "SWE", "company": "Acme", "url": "https://x/saved/1",
        "source": "manual", "location": "SF", "description": "d",
        "posted_date": None,
    })
    saved = discovery.score_page("SWE", "Acme", "python", url="https://x/saved/1")
    fresh = discovery.score_page("SWE", "Acme", "python", url="https://x/new/1")
    assert saved["already_saved"] is True
    assert fresh["already_saved"] is False


# --- band cutoffs ------------------------------------------------------------

@pytest.mark.parametrize("score,band", [
    (100, "strong"), (80, "strong"), (79, "good"), (60, "good"),
    (59, "fair"), (0, "fair"),
])
def test_band_cutoffs(score, band):
    assert discovery._band(score) == band
