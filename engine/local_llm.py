"""Bundled, offline local LLM tier (feature 005) — peer to basic_match.py.

Uses llama-cpp-python against a small Apache-2.0-licensed model bundled with
the installer (Qwen2.5-1.5B-Instruct, GGUF, Q4_K_M — see research.md §1),
so scoring/drafting/tailoring works with zero setup: no API key, no
internet connection. Lazily loaded behind a lock (model load is expensive)
so concurrent callers share one instance instead of each loading their own
copy of a ~1GB file.
"""
from __future__ import annotations

import logging
import threading
from pathlib import Path

log = logging.getLogger(__name__)

MODEL_FILENAME = "qwen2.5-1.5b-instruct-q4_k_m.gguf"

_lock = threading.Lock()
_model = None
_load_attempted = False


def _model_path() -> Path:
    from . import paths

    return paths.resource_path(f"models/{MODEL_FILENAME}")


def available() -> bool:
    return _model_path().exists()


def _llm_kwargs() -> dict:
    """013 (FR-005/006): GPU offload + CPU-thread tuning.

    n_gpu_layers: env JOBS_GPU_LAYERS, else -1 (auto — attempt full offload; a
    no-op on the CPU-only bundled wheel, a big win on a CUDA/Metal wheel).
    n_threads: env JOBS_LLM_THREADS, else all cores (llama.cpp otherwise
    under-uses them)."""
    import os

    threads_env = os.environ.get("JOBS_LLM_THREADS")
    gpu_env = os.environ.get("JOBS_GPU_LAYERS")
    return {
        "n_threads": int(threads_env) if threads_env else (os.cpu_count() or 1),
        "n_gpu_layers": int(gpu_env) if gpu_env not in (None, "") else -1,
    }


def _load_model(path: Path, n_ctx: int = 8192, _factory=None):
    """009 (FR-013): 8192 context — 4096 made long structured-extraction
    prompts overflow deterministically (Qwen2.5 supports 32k; the KV-cache
    cost at 8k for a 1.5B model is a couple hundred MB, acceptable).

    013: pass GPU/thread tuning; if constructing with GPU offload fails (a GPU
    wheel whose device init errors), retry ONCE on CPU (n_gpu_layers=0) so the
    offline path never breaks — graceful fallback, no error surfaced."""
    if _factory is None:
        from llama_cpp import Llama as _factory

    kwargs = _llm_kwargs()
    try:
        return _factory(model_path=str(path), n_ctx=n_ctx, verbose=False, **kwargs)
    except Exception:
        if kwargs.get("n_gpu_layers") == 0:
            raise  # already CPU — a real failure, let the caller handle it
        log.warning("model load with GPU offload failed; retrying on CPU",
                    exc_info=True)
        cpu_kwargs = dict(kwargs, n_gpu_layers=0)
        return _factory(model_path=str(path), n_ctx=n_ctx, verbose=False, **cpu_kwargs)


def _get_model():
    global _model, _load_attempted
    with _lock:
        if _model is not None:
            return _model
        if _load_attempted:
            return None
        _load_attempted = True
        path = _model_path()
        if not path.exists():
            return None
        try:
            _model = _load_model(path)
        except Exception:
            log.warning("failed to load local model at %s", path, exc_info=True)
            _model = None
        return _model


def chat(messages: list[dict], json_mode: bool = False) -> str:
    """Raises RuntimeError if the bundled model is missing or fails to load —
    callers (engine/matcher.py's tier dispatcher) treat this the same as a
    failed cloud call: fall through to the next tier.

    008 (FR-028): json_mode enables llama.cpp's grammar-constrained JSON
    decoding — the biggest reliability lever for small models: output is
    structurally valid JSON every time instead of best-effort prose."""
    model = _get_model()
    if model is None:
        raise RuntimeError("local model unavailable")
    kwargs = {"messages": messages, "temperature": 0.2}
    if json_mode:
        kwargs["response_format"] = {"type": "json_object"}
    completion = model.create_chat_completion(**kwargs)
    return completion["choices"][0]["message"]["content"] or ""
