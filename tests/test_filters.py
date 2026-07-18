"""T023: entry-level classifier accuracy gate + sponsorship phrase scan."""
from pathlib import Path

import yaml

from engine import filters

FIXTURE = Path(__file__).parent / "fixtures" / "titles.yml"


class TestEntryLevelClassifier:
    def _cases(self):
        return yaml.safe_load(FIXTURE.read_text(encoding="utf-8"))["cases"]

    def test_accuracy_gate_90_percent(self):
        cases = self._cases()
        wrong = [
            case
            for case in cases
            if filters.classify_entry_level(case["title"], case.get("description", ""))
            != case["entry"]
        ]
        accuracy = 1 - len(wrong) / len(cases)
        details = "; ".join(
            f"{c['title']!r} expected {c['entry']}" for c in wrong[:8]
        )
        assert accuracy >= 0.90, f"accuracy {accuracy:.0%}, misses: {details}"

    def test_seniority_always_wins(self):
        assert filters.classify_entry_level("Senior Software Engineer", "") is False
        assert filters.classify_entry_level("Senior FPGA Developer", "") is False
        assert filters.classify_entry_level("Staff Firmware Engineer", "") is False

    def test_new_grad_marker_always_passes(self):
        assert filters.classify_entry_level("Software Engineer, New Grad", "") is True
        assert filters.classify_entry_level("Software Engineer I", "") is True

    def test_engineer_levels_boundary(self):
        assert filters.classify_entry_level("Software Engineer I", "") is True
        assert filters.classify_entry_level("Software Engineer II", "") is False
        assert filters.classify_entry_level("Software Engineer III", "") is False

    def test_entry_markers_require_engineering_role(self):
        assert filters.classify_entry_level("Bridge Operations Associate", "") is False
        assert filters.classify_entry_level("New Grad Account Executive", "") is False
        assert filters.classify_entry_level("Associate Software Engineer", "") is True


class TestSponsorshipScan:
    def test_negative_phrases(self):
        for text in (
            "We are unable to sponsor visas at this time.",
            "US citizens only may apply.",
            "Applicants must not require sponsorship now or in the future.",
            "We will not sponsor work visas.",
            "This position requires an active security clearance.",
        ):
            flag, phrase = filters.scan_sponsorship(text)
            assert flag == -1, text
            assert phrase

    def test_positive_phrases(self):
        for text in (
            "Visa sponsorship available for exceptional candidates.",
            "We support H-1B transfers.",
            "OPT and CPT candidates are encouraged to apply.",
            "We will sponsor the right candidate.",
        ):
            flag, phrase = filters.scan_sponsorship(text)
            assert flag == 1, text

    def test_negative_overrides_positive(self):
        text = "Visa sponsorship available for some roles, but this role is unable to sponsor."
        flag, _ = filters.scan_sponsorship(text)
        assert flag == -1

    def test_neutral_text(self):
        flag, phrase = filters.scan_sponsorship("Build great software with us.")
        assert flag == 0 and phrase is None

    def test_opt_is_case_sensitive(self):
        flag, _ = filters.scan_sponsorship("We build options trading and adopt new tech.")
        assert flag == 0


class TestRating:
    def test_negative_jd_always_excluded(self):
        assert filters.rate_sponsorship(500, -1)[0] == "EXCLUDED"

    def test_positive_jd_is_high(self):
        assert filters.rate_sponsorship(0, 1)[0] == "HIGH"

    def test_strong_history_is_high(self):
        assert filters.rate_sponsorship(250, 0)[0] == "HIGH"

    def test_some_history_is_medium(self):
        assert filters.rate_sponsorship(3, 0)[0] == "MEDIUM"

    def test_no_signal_is_unknown(self):
        assert filters.rate_sponsorship(0, 0)[0] == "UNKNOWN"
