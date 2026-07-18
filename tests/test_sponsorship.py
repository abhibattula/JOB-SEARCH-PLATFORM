"""T024: company-name normalization, fuzzy employer matching, score derivation."""
from engine import db, sponsorship


class TestNormalization:
    def test_strips_legal_suffixes_and_case(self):
        assert db.normalize_company("NVIDIA Corp") == db.normalize_company(
            "NVIDIA CORPORATION"
        )
        assert db.normalize_company("Micron Technology, Inc.") == "micron technology"
        assert db.normalize_company("Advanced Micro Devices, Inc") == (
            "advanced micro devices"
        )


class TestEmployerMatching:
    EMPLOYERS = {
        "nvidia": ("NVIDIA CORPORATION", 1500),
        "qualcomm technologies": ("QUALCOMM Technologies, Inc.", 900),
        "micron technology": ("MICRON TECHNOLOGY, INC.", 700),
        "stripe": ("STRIPE, INC.", 300),
    }

    def test_exact_normalized_match(self):
        hit = sponsorship.match_employer("NVIDIA Corp", self.EMPLOYERS)
        assert hit is not None and hit[1] == 1500

    def test_fuzzy_match_above_threshold(self):
        hit = sponsorship.match_employer("Qualcomm Technologies Co", self.EMPLOYERS)
        assert hit is not None and hit[1] == 900

    def test_unrelated_name_no_match(self):
        assert sponsorship.match_employer("Totally Different LLC", self.EMPLOYERS) is None

    def test_short_name_matches_industry_suffixed_legal_name(self):
        employers = {
            "palantir technologies": ("PALANTIR TECHNOLOGIES INC", 400),
            "anthropic pbc": ("ANTHROPIC PBC", 60),
        }
        hit = sponsorship.match_employer("Palantir", employers)
        assert hit is not None and hit[1] == 400
        hit = sponsorship.match_employer("Anthropic", employers)
        assert hit is not None and hit[1] == 60


class TestScoreDerivation:
    def test_thresholds(self):
        assert sponsorship.score_from_approvals(250) == "HIGH"
        assert sponsorship.score_from_approvals(25) == "HIGH"
        assert sponsorship.score_from_approvals(24) == "MEDIUM"
        assert sponsorship.score_from_approvals(1) == "MEDIUM"
        assert sponsorship.score_from_approvals(0) == "UNKNOWN"


class TestApplyToCompanies:
    def test_companies_matched_and_marked(self, tmp_db):
        db.upsert_job(
            {
                "title": "HW Engineer",
                "company": "NVIDIA Corp",
                "url": "https://x.example/nv1",
                "source": "jobspy",
            }
        )
        sponsorship.store_employers(
            {"nvidia": {"display_name": "NVIDIA CORPORATION", "approvals": 1500}}
        )
        matched = sponsorship.apply_to_companies()
        assert matched == 1
        company = db.get_company_by_name("NVIDIA Corp")
        assert company["h1b_approvals"] == 1500
        assert company["sponsor_score"] == "HIGH"
        # second pass skips already-checked companies
        assert sponsorship.apply_to_companies() == 0
