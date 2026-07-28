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


def _completion_kwargs(payload: dict) -> dict:
    """016 (T020): the create_chat_completion kwargs — ALWAYS carries an
    explicit max_tokens (llama-cpp's None means 'generate to n_ctx')."""
    kwargs = {
        "messages": payload.get("messages") or [],
        "temperature": 0.2,
        "max_tokens": int(payload.get("max_tokens") or MAX_TOKENS_PROSE),
    }
    if payload.get("json_mode"):
        # 008 (FR-028): grammar-constrained JSON decoding — structurally
        # valid JSON every time instead of best-effort prose.
        kwargs["response_format"] = {"type": "json_object"}
    return kwargs


def _chat_impl(payload: dict) -> str:
    """Worker-side executor — runs ONLY on the engine/inference.py owner
    thread (015 FR-001: llama objects are not thread-safe; loading happens
    here too, so load and generate can never overlap)."""
    model = _get_model()
    if model is None:
        raise RuntimeError("local model unavailable")
    completion = model.create_chat_completion(**_completion_kwargs(payload))
    return completion["choices"][0]["message"]["content"] or ""


# 016 (T020, R13): explicit output caps per purpose — grammar-constrained
# JSON used to run unbounded to n_ctx (the riskiest generation, RC5).
MAX_TOKENS_JSON = 1536
MAX_TOKENS_PROSE = 768


def chat(messages: list[dict], json_mode: bool = False,
         timeout_s: float | None = None,
         max_tokens: int | None = None) -> str:
    """Raises RuntimeError if the bundled model is missing, fails to load,
    times out, or the AI queue is saturated — callers (engine/matcher.py's
    tier dispatcher) treat all of these the same as a failed cloud call:
    fall through to the next tier.

    015 (FR-001): routes through the single-owner inference worker, so every
    caller in the app is serialized onto one thread — the unserialized
    concurrent calls this replaces are what crashed the app natively
    (ggml-cpu.dll access violation). 016 (R13): every generation carries an
    explicit output cap."""
    from . import inference

    if max_tokens is None:
        max_tokens = MAX_TOKENS_JSON if json_mode else MAX_TOKENS_PROSE
    return inference.run_chat(messages, json_mode=json_mode,
                              timeout_s=timeout_s, max_tokens=max_tokens)
