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


class TestWageAndDenialCapture:
    """007-T031 (FR-010): loaders additionally capture denial counts and
    engineering wage data, tolerating files without those columns."""

    def _write_uscis(self, tmp_path, with_denials=True):
        columns = "Fiscal Year,Employer (Petitioner) Name,Initial Approval,Continuing Approval"
        row = "2024,GradeCo LLC,30,10"
        if with_denials:
            columns += ",Initial Denial,Continuing Denial"
            row += ",4,1"
        (tmp_path / "h1b_datahubexport-2024.csv").write_text(
            columns + "\n" + row + "\n", encoding="utf-8"
        )

    def test_uscis_denials_summed(self, tmp_path):
        self._write_uscis(tmp_path)
        employers, files = sponsorship.load_uscis_dir(tmp_path)
        assert files == 1
        record = employers["gradeco"]
        assert record["approvals"] == 40
        assert record["denials"] == 5

    def test_uscis_without_denial_columns_still_loads(self, tmp_path):
        self._write_uscis(tmp_path, with_denials=False)
        employers, _ = sponsorship.load_uscis_dir(tmp_path)
        record = employers["gradeco"]
        assert record["approvals"] == 40
        assert record.get("denials", 0) == 0

    def _write_dol(self, tmp_path, with_wages=True):
        columns = "EMPLOYER_NAME,JOB_TITLE,SOC_CODE"
        rows = [
            "GradeCo LLC,Software Engineer,15-1252",
            "GradeCo LLC,Hardware Engineer,17-2061",
            "GradeCo LLC,Accountant,13-2011",  # non-engineering: excluded
        ]
        if with_wages:
            columns += ",PW_WAGE_LEVEL,WAGE_RATE_OF_PAY_FROM"
            rows = [
                rows[0] + ",II,120000",
                rows[1] + ",IV,180000",
                rows[2] + ",I,90000",
            ]
        (tmp_path / "lca.csv").write_text(
            columns + "\n" + "\n".join(rows) + "\n", encoding="utf-8"
        )

    def test_dol_wage_levels_and_offered_medians(self, tmp_path):
        self._write_dol(tmp_path)
        employers = {"gradeco": {"display_name": "GradeCo LLC", "approvals": 40}}
        sponsorship.load_dol_dir(tmp_path, employers)
        record = employers["gradeco"]
        # engineering rows only (II, IV) — the accountant's I is excluded
        assert record["wage_level_median"] in ("II", "IV", "III")
        assert record["wage_offered_median"] == 150000.0

    def test_dol_without_wage_columns_behaves_as_before(self, tmp_path):
        self._write_dol(tmp_path, with_wages=False)
        employers = {"gradeco": {"display_name": "GradeCo LLC", "approvals": 40}}
        sponsorship.load_dol_dir(tmp_path, employers)
        record = employers["gradeco"]
        assert record.get("wage_level_median") is None
        assert "Software Engineer" in record["lca_titles"]


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
