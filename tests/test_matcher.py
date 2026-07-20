"""T031: LLM matcher — schema validation, retry-then-null, graceful no-key."""
import json

import pytest

from engine import matcher

VALID = json.dumps(
    {
        "match_score": 72,
        "matching_skills": ["Python", "Verilog"],
        "missing_skills": ["SystemVerilog UVM"],
        "gap_actions": [
            {"action": "Add a UVM testbench project", "impact": "Covers the top requirement"}
        ],
        "reasoning": "Solid fundamentals, missing verification methodology.",
    }
)


@pytest.fixture(autouse=True)
def llm_env(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("LLM_MIN_INTERVAL", "0")


class TestAnalyzeMatch:
    def test_valid_json_returns_analysis(self, monkeypatch):
        monkeypatch.setattr(matcher, "_chat", lambda messages: VALID)
        result = matcher.analyze_match("resume text", "HW Engineer", "NVIDIA", "jd text")
        assert result is not None
        assert result.match_score == 72
        assert result.gap_actions[0].action.startswith("Add a UVM")

    def test_invalid_then_valid_retries_once(self, monkeypatch):
        calls = []

        def chat(messages):
            calls.append(messages)
            return "not json at all" if len(calls) == 1 else VALID

        monkeypatch.setattr(matcher, "_chat", chat)
        result = matcher.analyze_match("resume", "Title", "Co", "jd")
        assert result is not None and len(calls) == 2

    def test_invalid_twice_returns_none(self, monkeypatch):
        monkeypatch.setattr(matcher, "_chat", lambda messages: "still not json")
        assert matcher.analyze_match("resume", "Title", "Co", "jd") is None

    def test_code_fenced_json_is_accepted(self, monkeypatch):
        monkeypatch.setattr(
            matcher, "_chat", lambda messages: f"```json\n{VALID}\n```"
        )
        assert matcher.analyze_match("resume", "Title", "Co", "jd") is not None

    def test_prompt_includes_resume_and_jd(self, monkeypatch):
        captured = {}

        def chat(messages):
            captured["text"] = json.dumps(messages)
            return VALID

        monkeypatch.setattr(matcher, "_chat", chat)
        matcher.analyze_match("MY RESUME TEXT", "Title", "Co", "THE JOB DESCRIPTION")
        assert "MY RESUME TEXT" in captured["text"]
        assert "THE JOB DESCRIPTION" in captured["text"]

    def test_no_tier_available_returns_none_without_calling(self, monkeypatch):
        """005: no cloud key AND no local model — neither tier available."""
        monkeypatch.delenv("LLM_API_KEY")
        monkeypatch.setattr(matcher.local_llm, "available", lambda: False)
        monkeypatch.setattr(
            matcher, "_chat", lambda messages: pytest.fail("must not call LLM")
        )
        assert matcher.analyze_match("resume", "Title", "Co", "jd") is None


class TestExtractSkills:
    def test_valid_array(self, monkeypatch):
        monkeypatch.setattr(
            matcher, "_chat", lambda messages: '["Python", "Verilog", "FPGA"]'
        )
        assert matcher.extract_skills("resume") == ["Python", "Verilog", "FPGA"]

    def test_failure_degrades_to_empty(self, monkeypatch):
        monkeypatch.setattr(matcher, "_chat", lambda messages: "oops")
        assert matcher.extract_skills("resume") == []

    def test_no_key_degrades_to_empty(self, monkeypatch):
        """005: no cloud key AND no local model — neither tier available."""
        monkeypatch.delenv("LLM_API_KEY")
        monkeypatch.setattr(matcher.local_llm, "available", lambda: False)
        assert matcher.extract_skills("resume") == []


class TestScoringTierDispatch:
    """005-T012: matcher._chat becomes a cloud -> local -> raise dispatcher;
    scoring_tier() reports which tier is currently active."""

    def test_scoring_tier_prefers_cloud_when_key_present(self, monkeypatch):
        monkeypatch.setenv("LLM_API_KEY", "test-key")
        monkeypatch.setattr(matcher.local_llm, "available", lambda: True)
        assert matcher.scoring_tier() == "cloud"

    def test_scoring_tier_falls_back_to_local_without_key(self, monkeypatch):
        monkeypatch.delenv("LLM_API_KEY")
        monkeypatch.setattr(matcher.local_llm, "available", lambda: True)
        assert matcher.scoring_tier() == "local"

    def test_scoring_tier_is_basic_when_neither_available(self, monkeypatch):
        monkeypatch.delenv("LLM_API_KEY")
        monkeypatch.setattr(matcher.local_llm, "available", lambda: False)
        assert matcher.scoring_tier() == "basic"

    def test_chat_dispatches_to_cloud_when_key_present(self, monkeypatch):
        monkeypatch.setenv("LLM_API_KEY", "test-key")
        monkeypatch.setattr(matcher.local_llm, "available", lambda: True)
        calls = []
        monkeypatch.setattr(matcher, "_chat_cloud", lambda messages: calls.append("cloud") or "ok")
        monkeypatch.setattr(matcher, "_chat_local", lambda messages: calls.append("local") or "ok")
        assert matcher._chat([{"role": "user", "content": "hi"}]) == "ok"
        assert calls == ["cloud"]

    def test_chat_dispatches_to_local_when_no_key(self, monkeypatch):
        monkeypatch.delenv("LLM_API_KEY")
        monkeypatch.setattr(matcher.local_llm, "available", lambda: True)
        calls = []
        monkeypatch.setattr(matcher, "_chat_cloud", lambda messages: calls.append("cloud") or "ok")
        monkeypatch.setattr(matcher, "_chat_local", lambda messages: calls.append("local") or "ok")
        assert matcher._chat([{"role": "user", "content": "hi"}]) == "ok"
        assert calls == ["local"]

    def test_chat_raises_when_neither_tier_available(self, monkeypatch):
        monkeypatch.delenv("LLM_API_KEY")
        monkeypatch.setattr(matcher.local_llm, "available", lambda: False)
        with pytest.raises(Exception):
            matcher._chat([{"role": "user", "content": "hi"}])

    def test_llm_available_true_via_local_tier_alone(self, monkeypatch):
        monkeypatch.delenv("LLM_API_KEY")
        monkeypatch.setattr(matcher.local_llm, "available", lambda: True)
        assert matcher.llm_available() is True
