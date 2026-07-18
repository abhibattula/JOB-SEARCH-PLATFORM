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

    def test_no_api_key_returns_none_without_calling(self, monkeypatch):
        monkeypatch.delenv("LLM_API_KEY")
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
        monkeypatch.delenv("LLM_API_KEY")
        assert matcher.extract_skills("resume") == []
