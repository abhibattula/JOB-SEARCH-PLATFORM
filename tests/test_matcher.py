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
        monkeypatch.setattr(matcher, "_chat", lambda messages, **kw: VALID)
        result = matcher.analyze_match("resume text", "HW Engineer", "NVIDIA", "jd text")
        assert result is not None
        assert result.match_score == 72
        assert result.gap_actions[0].action.startswith("Add a UVM")

    def test_invalid_then_valid_retries_once(self, monkeypatch):
        calls = []

        def chat(messages, **kw):
            calls.append(messages)
            return "not json at all" if len(calls) == 1 else VALID

        monkeypatch.setattr(matcher, "_chat", chat)
        result = matcher.analyze_match("resume", "Title", "Co", "jd")
        assert result is not None and len(calls) == 2

    def test_invalid_twice_returns_none(self, monkeypatch):
        monkeypatch.setattr(matcher, "_chat", lambda messages, **kw: "still not json")
        assert matcher.analyze_match("resume", "Title", "Co", "jd") is None

    def test_code_fenced_json_is_accepted(self, monkeypatch):
        monkeypatch.setattr(
            matcher, "_chat", lambda messages, **kw: f"```json\n{VALID}\n```"
        )
        assert matcher.analyze_match("resume", "Title", "Co", "jd") is not None

    def test_prompt_includes_resume_and_jd(self, monkeypatch):
        captured = {}

        def chat(messages, **kw):
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
            matcher, "_chat", lambda messages, **kw: pytest.fail("must not call LLM")
        )
        assert matcher.analyze_match("resume", "Title", "Co", "jd") is None


class TestExtractSkills:
    def test_valid_array(self, monkeypatch):
        monkeypatch.setattr(
            matcher, "_chat", lambda messages, **kw: '["Python", "Verilog", "FPGA"]'
        )
        assert matcher.extract_skills("resume") == ["Python", "Verilog", "FPGA"]

    def test_failure_degrades_to_empty(self, monkeypatch):
        monkeypatch.setattr(matcher, "_chat", lambda messages, **kw: "oops")
        assert matcher.extract_skills("resume") == []

    def test_no_key_degrades_to_empty(self, monkeypatch):
        """005: no cloud key AND no local model — neither tier available."""
        monkeypatch.delenv("LLM_API_KEY")
        monkeypatch.setattr(matcher.local_llm, "available", lambda: False)
        assert matcher.extract_skills("resume") == []


class TestScoringTierDispatch:
    """005-T012: matcher._chat becomes a cloud -> local -> raise dispatcher;
    scoring_tier() reports which tier is currently active."""

    def test_scoring_tier_prefers_cloud_when_key_present(self, tmp_db, monkeypatch):
        from engine import db as edb

        edb.set_setting("PREFER_LOCAL_LLM", "0")  # 009: offline is default
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

    def test_chat_dispatches_to_cloud_when_key_present(self, tmp_db, monkeypatch):
        from engine import db as edb

        edb.set_setting("PREFER_LOCAL_LLM", "0")  # 009: offline is default
        monkeypatch.setenv("LLM_API_KEY", "test-key")
        monkeypatch.setattr(matcher.local_llm, "available", lambda: True)
        calls = []
        monkeypatch.setattr(matcher, "_chat_cloud", lambda messages, **kw: calls.append("cloud") or "ok")
        monkeypatch.setattr(matcher, "_chat_local", lambda messages, **kw: calls.append("local") or "ok")
        assert matcher._chat([{"role": "user", "content": "hi"}]) == "ok"
        assert calls == ["cloud"]

    def test_chat_dispatches_to_local_when_no_key(self, monkeypatch):
        monkeypatch.delenv("LLM_API_KEY")
        monkeypatch.setattr(matcher.local_llm, "available", lambda: True)
        calls = []
        monkeypatch.setattr(matcher, "_chat_cloud", lambda messages, **kw: calls.append("cloud") or "ok")
        monkeypatch.setattr(matcher, "_chat_local", lambda messages, **kw: calls.append("local") or "ok")
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


class Test008ModelSplit:
    """008 US6 (T054/T055): structured tasks use the strict-JSON cloud model;
    the local tier gets constrained JSON decoding."""

    class _FakeCompletions:
        def __init__(self, record):
            self.record = record

        def create(self, **kwargs):
            self.record.append(kwargs)
            from types import SimpleNamespace

            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content="{}"))]
            )

    def _fake_openai(self, monkeypatch):
        record = []
        outer = self

        class FakeOpenAI:
            def __init__(self, base_url=None, api_key=None):
                from types import SimpleNamespace

                self.chat = SimpleNamespace(
                    completions=outer._FakeCompletions(record)
                )

        import openai

        monkeypatch.setattr(openai, "OpenAI", FakeOpenAI)
        monkeypatch.setattr(matcher.local_llm, "available", lambda: False)
        monkeypatch.setenv("LLM_API_KEY", "test-key")
        monkeypatch.setenv("LLM_MIN_INTERVAL", "0")
        return record

    def test_json_purpose_uses_strict_model_and_json_mode(self, tmp_db, monkeypatch):
        record = self._fake_openai(monkeypatch)
        matcher._chat([{"role": "user", "content": "extract"}], purpose="json")
        assert record[0]["model"] == "openai/gpt-oss-120b"
        assert record[0]["response_format"] == {"type": "json_object"}

    def test_prose_purpose_keeps_default_model(self, tmp_db, monkeypatch):
        record = self._fake_openai(monkeypatch)
        matcher._chat([{"role": "user", "content": "write a cover letter"}])
        assert record[0]["model"] == "llama-3.3-70b-versatile"
        assert "response_format" not in record[0]

    def test_local_json_purpose_requests_constrained_output(
        self, tmp_db, monkeypatch
    ):
        from engine import local_llm

        calls = []
        monkeypatch.delenv("LLM_API_KEY", raising=False)
        monkeypatch.setattr(local_llm, "available", lambda: True)
        monkeypatch.setattr(
            local_llm, "chat",
            lambda messages, json_mode=False: calls.append(json_mode) or "{}",
        )
        matcher._chat([{"role": "user", "content": "extract"}], purpose="json")
        assert calls == [True]


class Test009OfflineFirst:
    """009 US4 (T024): PREFER_LOCAL_LLM defaults ON — the bundled model
    serves all AI features even with a cloud key; the key is the automatic
    fallback when the local tier fails."""

    def test_default_prefers_local_when_model_available(self, tmp_db, monkeypatch):
        monkeypatch.setenv("LLM_API_KEY", "test-key")
        monkeypatch.setattr(matcher.local_llm, "available", lambda: True)
        assert matcher.scoring_tier() == "local"

    def test_toggle_off_prefers_cloud(self, tmp_db, monkeypatch):
        from engine import db as edb

        monkeypatch.setenv("LLM_API_KEY", "test-key")
        monkeypatch.setattr(matcher.local_llm, "available", lambda: True)
        edb.set_setting("PREFER_LOCAL_LLM", "0")
        assert matcher.scoring_tier() == "cloud"

    def test_no_local_model_still_cloud(self, tmp_db, monkeypatch):
        monkeypatch.setenv("LLM_API_KEY", "test-key")
        monkeypatch.setattr(matcher.local_llm, "available", lambda: False)
        assert matcher.scoring_tier() == "local" or matcher.scoring_tier() == "cloud"
        assert matcher.scoring_tier() == "cloud"

    def test_chat_uses_local_by_default_and_falls_through_on_failure(
        self, tmp_db, monkeypatch
    ):
        monkeypatch.setenv("LLM_API_KEY", "test-key")
        monkeypatch.setattr(matcher.local_llm, "available", lambda: True)
        calls = []

        def local_boom(messages, **kw):
            calls.append("local")
            raise RuntimeError("local model choked")

        monkeypatch.setattr(matcher, "_chat_local", local_boom)
        monkeypatch.setattr(
            matcher, "_chat_cloud",
            lambda messages, **kw: calls.append("cloud") or "cloud says hi",
        )
        result = matcher._chat([{"role": "user", "content": "hello"}])
        assert result == "cloud says hi"
        assert calls == ["local", "cloud"]

    def test_local_failure_without_key_reraises(self, tmp_db, monkeypatch):
        monkeypatch.delenv("LLM_API_KEY", raising=False)
        monkeypatch.setattr(matcher.local_llm, "available", lambda: True)

        def local_boom(messages, **kw):
            raise RuntimeError("local model choked")

        monkeypatch.setattr(matcher, "_chat_local", local_boom)
        with pytest.raises(RuntimeError, match="choked"):
            matcher._chat([{"role": "user", "content": "hello"}])
