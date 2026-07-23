"""008 US4 (T040): deterministic search-term derivation from the profile."""
from engine import search_terms


def profile_with(**overrides):
    profile = {
        "skills": ["Verilog", "Python", "FPGA"],
        "resume_sections": {
            "target_titles": ["Design Verification Engineer", "FPGA Engineer"],
            "experience": [
                {"title": "Hardware Engineering Intern"},
                {"title": "Research Assistant"},
            ],
        },
    }
    profile.update(overrides)
    return profile


class TestDerive:
    def test_targets_then_experience_then_skills_stable_order(self):
        terms = search_terms.derive(profile_with())
        assert terms[0] == "Design Verification Engineer"
        assert terms[1] == "FPGA Engineer"
        assert "entry level Hardware Engineering Intern" not in terms  # titles cleaned
        assert any("Hardware Engineering" in t for t in terms)
        assert terms == search_terms.derive(profile_with())  # deterministic

    def test_capped_at_eight(self):
        profile = profile_with()
        profile["resume_sections"]["target_titles"] = [f"Title {i}" for i in range(12)]
        assert len(search_terms.derive(profile)) <= search_terms.MAX_TERMS

    def test_empty_profile_derives_nothing(self):
        assert search_terms.derive({}) == []
        assert search_terms.derive({"resume_sections": None, "skills": []}) == []

    def test_no_duplicate_terms(self):
        profile = profile_with()
        profile["resume_sections"]["experience"] = [
            {"title": "FPGA Engineer"},  # duplicates a target title
        ]
        terms = search_terms.derive(profile)
        assert len(terms) == len({t.casefold() for t in terms})
