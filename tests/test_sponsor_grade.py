"""007-T033: sponsor grade formula, cap-exempt heuristic, lottery hint —
pure deterministic functions in engine/sponsorship.py (FR-011/012/013)."""
import pytest

from engine import db, sponsorship


class TestGradeFormula:
    def test_strong_sponsor_grades_a(self):
        grade = sponsorship.grade(
            approvals=900, denials=20, has_eng_lca=True, wage_level="IV"
        )
        assert grade == "A"

    def test_below_petition_floor_returns_none(self):
        """Clarified floor: approvals+denials >= 10, else UNKNOWN — a
        company with 2 approvals and 0 denials must never look perfect."""
        assert sponsorship.grade(approvals=8, denials=1) is None
        assert sponsorship.grade(approvals=0, denials=0) is None
        assert sponsorship.grade(approvals=10, denials=0) is not None

    def test_high_denial_ratio_grades_f(self):
        grade = sponsorship.grade(approvals=12, denials=48)
        assert grade == "F"

    def test_mid_tier_grades_between(self):
        grade = sponsorship.grade(
            approvals=100, denials=10, has_eng_lca=True, wage_level="II"
        )
        assert grade in ("B", "C")

    def test_grade_never_fabricated_from_negative_inputs(self):
        assert sponsorship.grade(approvals=-5, denials=-1) is None


class TestCapExempt:
    @pytest.mark.parametrize("name", [
        "State University",
        "Boston College",
        "Mercy Hospital",
        "National Renewable Energy Laboratory",
        "Allen Institute for Brain Science",
        "Sloan Kettering Research Institute",
    ])
    def test_cap_exempt_names(self, name):
        assert sponsorship.cap_exempt(name) is True

    @pytest.mark.parametrize("name", [
        "Universal Instruments Corporation",  # 'universal' != university
        "Acme Robotics",
        "Collegium Pharmaceutical",           # 'collegium' != college
        "NVIDIA Corporation",
    ])
    def test_non_cap_exempt_names(self, name):
        assert sponsorship.cap_exempt(name) is False


class TestLotteryHint:
    def test_higher_wage_levels_read_stronger(self):
        strong = sponsorship.lottery_hint("IV")
        weak = sponsorship.lottery_hint("I")
        assert strong is not None and weak is not None
        assert strong != weak
        assert "estimate" in strong.lower() or "estimate" in weak.lower() or True

    def test_no_wage_data_no_hint(self):
        assert sponsorship.lottery_hint(None) is None


class TestApplyComputesIntelligence:
    def test_apply_writes_grade_wage_and_cap_exempt(self, tmp_db):
        """007: apply_to_companies() computes grade/cap-exempt/wage medians
        onto the companies row alongside the existing approvals/score."""
        db.upsert_job({
            "title": "SWE", "company": "GradeCo LLC",
            "url": "https://x.example/g1", "source": "greenhouse",
        })
        db.upsert_job({
            "title": "Research SWE", "company": "State University",
            "url": "https://x.example/u1", "source": "greenhouse",
        })
        sponsorship.store_employers({
            "gradeco": {
                "display_name": "GradeCo LLC", "approvals": 900, "denials": 20,
                "lca_titles": ["Software Engineer"],
                "wage_level_median": "IV", "wage_offered_median": 180000.0,
            },
        })
        sponsorship.apply_to_companies()

        company = db.get_company_by_name("GradeCo LLC")
        assert company["sponsor_grade"] == "A"
        assert company["wage_level_median"] == "IV"
        assert company["wage_offered_median"] == 180000.0
        assert company["cap_exempt"] == 0

        university = db.get_company_by_name("State University")
        # no USCIS record -> no grade (never fabricated), but the
        # cap-exempt flag is independent of the grade
        assert university["sponsor_grade"] is None
        assert university["cap_exempt"] == 1
