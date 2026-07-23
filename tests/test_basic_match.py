"""004-WS-E: deterministic local match scoring (no API key needed)."""
from engine import basic_match, db

RESUME = """
ABHINAV B — Computer Engineering, 2026
Skills: Python, Verilog, SystemVerilog, FPGA prototyping, embedded C,
UART and SPI protocols, Git, Linux. Projects: RISC-V core on FPGA,
UVM testbench for an ALU, Flask web service with SQL database.
"""

HW_JD = """
We are seeking a New College Grad Hardware Engineer. You will write RTL in
SystemVerilog, build UVM testbenches, and debug FPGA prototypes. Familiarity
with SPI, I2C, and timing analysis is a plus. Python scripting required.
"""

SALES_JD = "Drive revenue growth through consultative enterprise selling."


class TestSkillExtraction:
    def test_finds_skills_in_resume(self):
        skills = basic_match.extract_skills(RESUME)
        for expected in ("python", "verilog", "systemverilog", "fpga", "uvm", "spi", "linux"):
            assert expected in skills, expected

    def test_no_false_hits_in_prose(self):
        skills = basic_match.extract_skills(
            "I enjoy carpentry, javelin, and reading about armadillos."
        )
        assert skills == set()


class TestScoring:
    def test_deterministic(self):
        a = basic_match.score(RESUME, "Hardware Engineer", HW_JD)
        b = basic_match.score(RESUME, "Hardware Engineer", HW_JD)
        assert a.match_score == b.match_score

    def test_strong_overlap_beats_no_overlap(self):
        strong = basic_match.score(RESUME, "Hardware Engineer", HW_JD)
        weak = basic_match.score(RESUME, "Account Executive", SALES_JD)
        assert strong.match_score > weak.match_score
        assert strong.match_score >= 60

    def test_reports_matching_and_missing(self):
        result = basic_match.score(RESUME, "Hardware Engineer", HW_JD)
        assert "systemverilog" in [s.lower() for s in result.matching_skills]
        assert "i2c" in [s.lower() for s in result.missing_skills]
        assert result.gap_actions  # templated suggestions exist
        assert result.reasoning

    def test_jd_without_signals_scores_neutral(self):
        result = basic_match.score(RESUME, "Engineer", "Great culture. Apply now.")
        assert 30 <= result.match_score <= 55

    def test_extra_skills_from_profile_boost_matching(self):
        """006-E: a skill the user explicitly lists in their Profile (but
        that the resume-text regex extraction missed or phrased
        differently) should still count as a match, improving accuracy for
        no-cloud-key users."""
        without_extra = basic_match.score(RESUME, "Hardware Engineer", HW_JD)
        assert "i2c" in [s.lower() for s in without_extra.missing_skills]

        with_extra = basic_match.score(RESUME, "Hardware Engineer", HW_JD, extra_skills={"i2c"})
        assert "i2c" in [s.lower() for s in with_extra.matching_skills]
        assert "i2c" not in [s.lower() for s in with_extra.missing_skills]
        assert with_extra.match_score >= without_extra.match_score

    def test_extra_skills_none_behaves_same_as_omitted(self):
        a = basic_match.score(RESUME, "Hardware Engineer", HW_JD)
        b = basic_match.score(RESUME, "Hardware Engineer", HW_JD, extra_skills=None)
        assert a.match_score == b.match_score


class TestUpgradePath:
    def _seed(self, method):
        db.upsert_job(
            {
                "title": f"HW Engineer {method}",
                "company": "TestCo",
                "url": f"https://x.example/{method}",
                "source": "greenhouse",
                "description": "verilog fpga",
            }
        )
        jobs, _ = db.query_jobs(window=None, statuses=None, entry_level=None)
        job = next(j for j in jobs if j["url"].endswith(method))
        db.set_classification(job["id"], True, "UNKNOWN", None)
        db.set_match(job["id"], 55.0, '{"match_score": 55, "method": "%s"}' % method)
        return job["id"]

    def test_basic_scores_are_rescoreable_when_llm_arrives(self, tmp_db):
        basic_id = self._seed("basic")
        self._seed("llm")
        upgradable = db.jobs_needing_score(include_basic=True)
        ids = {j["id"] for j in upgradable}
        assert basic_id in ids
        assert len(ids) == 1  # llm-scored job is never re-scored

    def test_default_query_skips_all_scored(self, tmp_db):
        self._seed("basic")
        assert db.jobs_needing_score() == []

    def test_upgrade_methods_basic_and_local_when_cloud_tier_arrives(self, tmp_db):
        """005-T016: cloud tier available -> both basic- and local-scored
        jobs are eligible for rescoring; llm-scored jobs are never redone."""
        basic_id = self._seed("basic")
        local_id = self._seed("local")
        self._seed("llm")
        upgradable = db.jobs_needing_score(upgrade_methods=("basic", "local"))
        ids = {j["id"] for j in upgradable}
        assert ids == {basic_id, local_id}

    def test_upgrade_methods_basic_only_when_local_tier_arrives(self, tmp_db):
        """005-T016: local tier available (no cloud key) -> only basic-scored
        jobs are eligible; local-scored jobs stay (nothing better locally)."""
        basic_id = self._seed("basic")
        self._seed("local")
        upgradable = db.jobs_needing_score(upgrade_methods=("basic",))
        ids = {j["id"] for j in upgradable}
        assert ids == {basic_id}
