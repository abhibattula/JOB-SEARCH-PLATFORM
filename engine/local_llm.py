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


def _load_model(path: Path):
    from llama_cpp import Llama

    return Llama(model_path=str(path), n_ctx=4096, verbose=False)


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
