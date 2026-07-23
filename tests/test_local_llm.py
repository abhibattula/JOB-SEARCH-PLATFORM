"""009 US3 (T017): the local model must load with enough context for
chunked extraction (root cause B2: n_ctx=4096 vs long prompts)."""
from engine import local_llm


class TestContextWindow:
    def test_model_loads_with_8192_context(self, monkeypatch):
        captured = {}

        class FakeLlama:
            def __init__(self, model_path=None, n_ctx=None, **kw):
                captured["n_ctx"] = n_ctx

        import llama_cpp

        monkeypatch.setattr(llama_cpp, "Llama", FakeLlama)
        local_llm._load_model.__wrapped__ if hasattr(local_llm._load_model, "__wrapped__") else None
        local_llm._load_model("C:/fake/model.gguf")
        assert captured["n_ctx"] == 8192
