"""005-T011: engine/local_llm.py — the bundled offline LLM tier.

The real ~1GB model is never loaded in unit tests; llama_cpp's Llama is
mocked via local_llm._load_model so these tests stay fast and deterministic.
"""
import pytest

from engine import local_llm


@pytest.fixture(autouse=True)
def _reset_singleton(monkeypatch):
    """Each test gets a clean lazy-load state — the module-level singleton
    must not leak between tests."""
    monkeypatch.setattr(local_llm, "_model", None)
    monkeypatch.setattr(local_llm, "_load_attempted", False)


class TestAvailable:
    def test_unavailable_when_model_file_missing(self, monkeypatch, tmp_path):
        monkeypatch.setattr(local_llm, "_model_path", lambda: tmp_path / "missing.gguf")
        assert local_llm.available() is False

    def test_available_when_model_file_present(self, monkeypatch, tmp_path):
        model_file = tmp_path / "present.gguf"
        model_file.write_bytes(b"fake")
        monkeypatch.setattr(local_llm, "_model_path", lambda: model_file)
        assert local_llm.available() is True


class FakeLlama:
    def __init__(self, reply="Hello from local model"):
        self.reply = reply
        self.calls = []

    def create_chat_completion(self, messages, temperature=0.2):
        self.calls.append(messages)
        return {"choices": [{"message": {"content": self.reply}}]}


class TestChat:
    def test_chat_returns_model_reply(self, monkeypatch, tmp_path):
        model_file = tmp_path / "present.gguf"
        model_file.write_bytes(b"fake")
        monkeypatch.setattr(local_llm, "_model_path", lambda: model_file)
        fake = FakeLlama(reply="draft answer")
        monkeypatch.setattr(local_llm, "_load_model", lambda path: fake)

        result = local_llm.chat([{"role": "user", "content": "hi"}])

        assert result == "draft answer"
        assert fake.calls == [[{"role": "user", "content": "hi"}]]

    def test_chat_raises_when_model_file_missing(self, monkeypatch, tmp_path):
        monkeypatch.setattr(local_llm, "_model_path", lambda: tmp_path / "missing.gguf")
        with pytest.raises(RuntimeError):
            local_llm.chat([{"role": "user", "content": "hi"}])

    def test_chat_raises_when_load_fails(self, monkeypatch, tmp_path):
        model_file = tmp_path / "present.gguf"
        model_file.write_bytes(b"fake")
        monkeypatch.setattr(local_llm, "_model_path", lambda: model_file)

        def _boom(path):
            raise OSError("corrupt model file")

        monkeypatch.setattr(local_llm, "_load_model", _boom)
        with pytest.raises(RuntimeError):
            local_llm.chat([{"role": "user", "content": "hi"}])

    def test_model_loaded_only_once_across_multiple_chat_calls(self, monkeypatch, tmp_path):
        model_file = tmp_path / "present.gguf"
        model_file.write_bytes(b"fake")
        monkeypatch.setattr(local_llm, "_model_path", lambda: model_file)
        fake = FakeLlama()
        load_calls = []

        def _load(path):
            load_calls.append(path)
            return fake

        monkeypatch.setattr(local_llm, "_load_model", _load)
        local_llm.chat([{"role": "user", "content": "one"}])
        local_llm.chat([{"role": "user", "content": "two"}])

        assert len(load_calls) == 1
