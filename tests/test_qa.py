"""010 T016: grounded AI drafting for open-ended application questions.
Fail-closed on sensitive questions, grounded only in the user's real data,
concise, and refusal-over-fabrication when grounding is thin."""
import pytest

from engine import qa


@pytest.fixture(autouse=True)
def _llm_available(monkeypatch):
    # drafting gates on matcher.llm_available(); make it deterministic so
    # tests don't depend on whether this machine has the bundled model
    from engine import matcher

    monkeypatch.setattr(matcher, "llm_available", lambda: True)


@pytest.fixture
def profile():
    return {
        "resume_text": (
            "Abhinav Battula — Computer Engineer. Hardware Engineering Intern "
            "at Aurora Semiconductors: built UVM testbenches for a PCIe Gen5 "
            "controller, raised coverage 71%->94%. Skills: SystemVerilog, UVM, "
            "Python, RISC-V."
        ),
        "first_name": "Abhinav",
    }


JOB = {"title": "Verification Engineer", "company": "Figma",
       "description": "Own UVM verification for our silicon."}


class TestEligibility:
    def test_sensitive_tags_never_eligible(self):
        for tag in ("work_authorization", "sponsorship_requirement",
                    "eeo_disclosure", "login_password", "login_email"):
            assert not qa.is_ai_eligible(tag)

    def test_open_ended_tags_eligible(self):
        assert qa.is_ai_eligible("cover_letter")
        assert qa.is_ai_eligible("free_text_unknown")

    def test_eligibility_is_allowlist_not_blocklist(self):
        # an unknown/novel tag must default to NOT eligible (fail-closed)
        assert not qa.is_ai_eligible("some_new_tag_we_never_saw")


class TestDrafting:
    def test_sensitive_question_returns_none_without_calling_model(
            self, profile, monkeypatch):
        called = []
        monkeypatch.setattr(qa, "_generate", lambda *a, **k: called.append(1) or "x")
        result = qa.draft("Are you authorized to work in the US?",
                          "work_authorization", profile, JOB)
        assert result is None
        assert not called  # fail-closed BEFORE any model call

    def test_grounded_draft_returned_for_essay(self, profile, monkeypatch):
        monkeypatch.setattr(
            qa, "_generate",
            lambda prompt, maxlen: "I built UVM testbenches for a PCIe Gen5 "
            "controller at Aurora, which maps directly to owning verification "
            "at Figma.")
        result = qa.draft("Why do you want to work here?",
                          "free_text_unknown", profile, JOB)
        assert result and "UVM" in result

    def test_refuses_on_thin_grounding(self, monkeypatch):
        # empty resume/profile -> no grounding -> None, never fabricate
        monkeypatch.setattr(qa, "_generate",
                            lambda prompt, maxlen: "generic filler")
        result = qa.draft("Why us?", "free_text_unknown",
                          {"resume_text": ""}, JOB)
        assert result is None

    def test_model_refusal_token_yields_none(self, profile, monkeypatch):
        monkeypatch.setattr(qa, "_generate", lambda prompt, maxlen: "CANNOT_ANSWER")
        assert qa.draft("Why us?", "free_text_unknown", profile, JOB) is None

    def test_empty_model_output_yields_none(self, profile, monkeypatch):
        monkeypatch.setattr(qa, "_generate", lambda prompt, maxlen: "   ")
        assert qa.draft("Why us?", "free_text_unknown", profile, JOB) is None

    def test_prompt_is_bounded_and_grounded(self, profile, monkeypatch):
        captured = {}

        def fake_generate(prompt, maxlen):
            captured["prompt"] = prompt
            captured["maxlen"] = maxlen
            return "A grounded answer about UVM verification work."

        monkeypatch.setattr(qa, "_generate", fake_generate)
        qa.draft("Describe a project.", "free_text_unknown", profile, JOB)
        # grounding present, prompt bounded, job context included
        assert "UVM" in captured["prompt"] or "Aurora" in captured["prompt"]
        assert "Figma" in captured["prompt"]
        assert len(captured["prompt"]) <= qa.MAX_PROMPT_CHARS

    def test_maxlength_shrinks_target(self, profile, monkeypatch):
        captured = {}
        monkeypatch.setattr(qa, "_generate",
                            lambda prompt, maxlen: captured.update(maxlen=maxlen)
                            or "short")
        qa.draft("Why?", "free_text_unknown", profile, JOB, maxlength=80)
        assert captured["maxlen"] <= 80


class TestSaneLength:
    def test_default_target_is_concise(self):
        # 60-120 words per FR-011 -> target char budget in that ballpark
        assert 300 <= qa.DEFAULT_MAXLEN <= 900
