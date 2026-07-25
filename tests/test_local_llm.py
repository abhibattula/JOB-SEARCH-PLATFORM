"""009 US3 (T017): the local model must load with enough context for
chunked extraction (root cause B2: n_ctx=4096 vs long prompts)."""
from engine import local_llm


class TestContextWindow:
    def test_model_loads_with_8192_context(self):
        # 014 (CI green on Linux): inject the Llama factory instead of
        # `import llama_cpp` — llama-cpp-python is pinned to win32/darwin only
        # (not in the Linux CI's requirements), so importing it hard-failed the
        # whole CI job. The injection seam needs no real module.
        captured = {}

        def fake_llama(model_path=None, n_ctx=None, **kw):
            captured["n_ctx"] = n_ctx
            return object()

        local_llm._load_model("C:/fake/model.gguf", _factory=fake_llama)
        assert captured["n_ctx"] == 8192


class TestGpuAndThreads013:
    """013: offline model GPU offload + CPU-thread tuning with graceful CPU
    fallback. No real model loads — the Llama factory is injected."""

    def test_llm_kwargs_defaults(self, monkeypatch):
        import os
        monkeypatch.delenv("JOBS_LLM_THREADS", raising=False)
        monkeypatch.delenv("JOBS_GPU_LAYERS", raising=False)
        kw = local_llm._llm_kwargs()
        assert kw["n_threads"] == (os.cpu_count() or 1)
        assert kw["n_gpu_layers"] == -1   # auto: attempt full offload

    def test_llm_kwargs_env_overrides(self, monkeypatch):
        monkeypatch.setenv("JOBS_LLM_THREADS", "3")
        monkeypatch.setenv("JOBS_GPU_LAYERS", "10")
        kw = local_llm._llm_kwargs()
        assert kw["n_threads"] == 3
        assert kw["n_gpu_layers"] == 10

    def test_load_model_passes_gpu_and_threads(self, monkeypatch, tmp_path):
        monkeypatch.setenv("JOBS_LLM_THREADS", "5")
        monkeypatch.setenv("JOBS_GPU_LAYERS", "-1")
        seen = {}

        def fake_llama(**kwargs):
            seen.update(kwargs)
            return object()

        model = local_llm._load_model(tmp_path / "m.gguf", _factory=fake_llama)
        assert model is not None
        assert seen["n_threads"] == 5
        assert seen["n_gpu_layers"] == -1

    def test_graceful_gpu_to_cpu_fallback(self, monkeypatch, tmp_path):
        monkeypatch.setenv("JOBS_GPU_LAYERS", "-1")
        calls = []

        def flaky_llama(**kwargs):
            calls.append(kwargs["n_gpu_layers"])
            if kwargs["n_gpu_layers"] != 0:
                raise RuntimeError("no CUDA device")
            return "cpu-model"

        model = local_llm._load_model(tmp_path / "m.gguf", _factory=flaky_llama)
        assert model == "cpu-model"
        assert calls == [-1, 0]   # tried GPU, then fell back to CPU
