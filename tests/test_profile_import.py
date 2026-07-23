"""009 US3 (T019): background profile import — state machine, proposal
building, and apply semantics. No real LLM: extraction layers are
monkeypatched; `background=False` keeps everything deterministic."""
import pytest

from engine import db, profile_import
from engine.resume_extract import Contact, ResumeSections


@pytest.fixture(autouse=True)
def _reset(tmp_db):
    profile_import.reset_state()
    yield
    profile_import.reset_state()


def stub_extraction(monkeypatch, sections=None, contact=None, skills=None,
                    fail_with=None):
    from engine import matcher, resume_extract

    if fail_with is not None:
        def boom(text, on_progress=None):
            raise RuntimeError(fail_with)
        monkeypatch.setattr(resume_extract, "extract", boom)
    else:
        monkeypatch.setattr(
            resume_extract, "extract",
            lambda text, on_progress=None: sections,
        )
    monkeypatch.setattr(
        resume_extract, "extract_contact",
        lambda text: contact if contact is not None else Contact(),
    )
    monkeypatch.setattr(matcher, "extract_skills", lambda text: skills or [])


class TestStateMachine:
    def test_no_resume_on_file_refuses(self, monkeypatch):
        assert profile_import.start_import(background=False) is False
        assert profile_import.status()["state"] == "idle"

    def test_full_run_reaches_ready_with_proposal(self, monkeypatch):
        db.save_profile(resume_text="resume text", resume_filename="r.pdf")
        stub_extraction(
            monkeypatch,
            sections=ResumeSections(
                experience=[{"title": "Intern", "organization": "Acme"}],
                skills=["Verilog"],
                target_titles=["FPGA Engineer"],
                contact=Contact(first_name="Abhinav", email="abhi@x.com"),
            ),
            skills=["Python"],
        )
        assert profile_import.start_import(background=False) is True
        status = profile_import.status()
        assert status["state"] == "ready"
        assert status["error"] is None
        proposal = profile_import.proposal()
        assert proposal is not None
        assert proposal["resume_filename"] == "r.pdf"

    def test_concurrent_start_refused(self, monkeypatch):
        db.save_profile(resume_text="resume text")
        with profile_import._lock:
            profile_import._state["state"] = "extracting"
        assert profile_import.start_import(background=False) is False

    def test_failure_carries_real_error(self, monkeypatch):
        db.save_profile(resume_text="resume text")
        stub_extraction(monkeypatch, fail_with="model exploded spectacularly")
        profile_import.start_import(background=False)
        status = profile_import.status()
        assert status["state"] == "failed"
        assert "spectacularly" in status["error"]


class TestProposalMatrix:
    def _run(self, monkeypatch, **stub_kwargs):
        stub_extraction(monkeypatch, **stub_kwargs)
        assert profile_import.start_import(background=False) is True
        return profile_import.proposal()

    def field(self, proposal, name):
        return next(f for f in proposal["fields"] if f["field"] == name)

    def test_blank_current_defaults_apply(self, monkeypatch):
        db.save_profile(resume_text="t")
        proposal = self._run(
            monkeypatch,
            sections=ResumeSections(contact=Contact(email="new@x.com")),
        )
        email = self.field(proposal, "email")
        assert email["current"] in ("", None)
        assert email["proposed"] == "new@x.com"
        assert email["default"] == "apply"

    def test_conflict_defaults_keep(self, monkeypatch):
        db.save_profile(resume_text="t", email="mine@x.com")
        proposal = self._run(
            monkeypatch,
            sections=ResumeSections(contact=Contact(email="other@x.com")),
        )
        email = self.field(proposal, "email")
        assert email["default"] == "keep"

    def test_identical_marks_no_change(self, monkeypatch):
        db.save_profile(resume_text="t", email="same@x.com")
        proposal = self._run(
            monkeypatch,
            sections=ResumeSections(contact=Contact(email="same@x.com")),
        )
        assert self.field(proposal, "email")["default"] == "none"

    def test_lists_default_merge(self, monkeypatch):
        db.save_profile(resume_text="t", skills=["Python"])
        proposal = self._run(
            monkeypatch,
            sections=ResumeSections(skills=["Verilog"]),
            skills=["FPGA"],
        )
        skills = self.field(proposal, "skills")
        assert skills["default"] == "merge"
        assert set(skills["proposed"]) >= {"Verilog", "FPGA"}

    def test_edited_sections_default_keep_with_warning(self, monkeypatch):
        db.save_profile(resume_text="t",
                        resume_sections={"experience": [{"title": "Old"}]},
                        sections_edited_at="2026-06-01 10:00:00.000000")
        proposal = self._run(
            monkeypatch,
            sections=ResumeSections(experience=[{"title": "New"}]),
        )
        sections = self.field(proposal, "resume_sections")
        assert sections["default"] == "keep"
        assert sections["edited_at"]

    def test_visa_fields_never_in_proposal(self, monkeypatch):
        db.save_profile(resume_text="t")
        proposal = self._run(
            monkeypatch,
            sections=ResumeSections(contact=Contact(email="e@x.com")),
        )
        names = {f["field"] for f in proposal["fields"]}
        assert "visa_status" not in names
        assert "authorized_without_sponsorship" not in names

    def test_zero_differences_flagged(self, monkeypatch):
        db.save_profile(resume_text="t", email="same@x.com")
        proposal = self._run(
            monkeypatch,
            sections=ResumeSections(contact=Contact(email="same@x.com")),
        )
        assert proposal["has_differences"] is False

    def test_regex_contact_fallback_used_when_llm_gives_none(self, monkeypatch):
        db.save_profile(resume_text="t")
        proposal = self._run(
            monkeypatch,
            sections=None,  # local extraction produced nothing
            contact=Contact(email="regex@x.com", phone="(512) 555-0100"),
        )
        assert self.field(proposal, "email")["proposed"] == "regex@x.com"


class TestApply:
    def _ready(self, monkeypatch, **stub_kwargs):
        stub_extraction(monkeypatch, **stub_kwargs)
        assert profile_import.start_import(background=False) is True

    def test_apply_and_keep_decisions(self, monkeypatch):
        db.save_profile(resume_text="t", email="mine@x.com", phone="")
        self._ready(monkeypatch, sections=ResumeSections(
            contact=Contact(email="other@x.com", phone="(512) 555-0100"),
        ))
        result = profile_import.apply_import(
            {"email": "keep", "phone": "apply"}
        )
        profile = db.get_profile()
        assert profile["email"] == "mine@x.com"
        assert "512" in profile["phone"]
        assert "phone" in result["applied"] and "email" not in result["applied"]
        # proposal consumed
        assert profile_import.proposal() is None
        assert profile_import.status()["state"] == "applied"

    def test_merge_decision_unions_lists(self, monkeypatch):
        db.save_profile(resume_text="t", skills=["Python"])
        self._ready(monkeypatch, sections=ResumeSections(skills=["Verilog"]))
        profile_import.apply_import({"skills": "merge"})
        skills = db.get_profile()["skills"]
        assert "Python" in skills and "Verilog" in skills

    def test_applying_sections_is_the_consent(self, monkeypatch):
        db.save_profile(resume_text="t",
                        resume_sections={"experience": [{"title": "Old"}]},
                        sections_edited_at="2026-06-01 10:00:00.000000")
        self._ready(monkeypatch, sections=ResumeSections(
            experience=[{"title": "New", "organization": "Acme"}],
        ))
        profile_import.apply_import({"resume_sections": "apply"})
        profile = db.get_profile()
        assert profile["resume_sections"]["experience"][0]["title"] == "New"
        assert not profile.get("sections_edited_at")

    def test_search_terms_rederive_unless_user_owned(self, monkeypatch):
        db.save_profile(resume_text="t")
        self._ready(monkeypatch, sections=ResumeSections(
            target_titles=["FPGA Engineer"],
        ))
        profile_import.apply_import({"resume_sections": "apply",
                                     "target_titles": "apply"})
        stored = db.get_profile()["search_terms"]
        assert stored and "FPGA Engineer" in stored["terms"]
        # user-owned terms are never clobbered
        db.save_profile(search_terms={"terms": ["my own"],
                                      "derived_from": "user"})
        profile_import.reset_state()
        self._ready(monkeypatch, sections=ResumeSections(
            target_titles=["Other Title"],
        ))
        profile_import.apply_import({"resume_sections": "apply"})
        assert db.get_profile()["search_terms"]["terms"] == ["my own"]

    def test_apply_without_proposal_raises(self):
        with pytest.raises(RuntimeError):
            profile_import.apply_import({"email": "apply"})
