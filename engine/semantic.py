"""Offline semantic pre-ranking (feature 008, FR-029).

EmbeddingGemma-300M (Q8_0 GGUF, ~330MB, bundled) runs through the
already-shipped llama-cpp-python stack — no new packages, no network, no
key. New jobs and the resume get embedded once; scoring then spends the
limited AI quota top-down by cosine similarity instead of blindly by date.
Research basis (ConFit v3, Resume2Vec): embedding-rank + LLM-rerank beats
raw LLM scoring of everything. Every path degrades gracefully — a missing
model or failed embedding just means the previous date ordering.
"""
from __future__ import annotations

import logging
import math
import struct
import threading

log = logging.getLogger(__name__)

MODEL_RELPATH = "models/embeddinggemma-300M-Q8_0.gguf"
MAX_EMBED_CHARS = 4000

_model = None
_lock = threading.Lock()


def _model_path():
    from . import paths

    return paths.resource_path(MODEL_RELPATH)


def available() -> bool:
    try:
        return _model_path().exists()
    except Exception:
        return False


# 016 (T020, R13): one load attempt per session — a failing 330 MB load
# used to be re-attempted on EVERY embed call.
_load_attempted = False


def _load():
    global _model, _load_attempted
    with _lock:
        if _model is None:
            if _load_attempted:
                raise RuntimeError(
                    "embedding model previously failed to load this session")
            _load_attempted = True
            from llama_cpp import Llama
            from .local_llm import _llm_kwargs

            # 013: GPU offload + CPU threads (graceful CPU fallback), same as
            # the chat model — a no-op on the CPU wheel, a win on a GPU wheel.
            # 016 (R13): n_batch capped — the scores buffer is
            # n_batch × n_vocab × 4 bytes (≈537 MB at the default 512).
            kwargs = _llm_kwargs()
            try:
                _model = Llama(model_path=str(_model_path()), embedding=True,
                               n_ctx=2048, n_batch=256, verbose=False,
                               **kwargs)
            except Exception:
                cpu = dict(kwargs, n_gpu_layers=0)
                _model = Llama(model_path=str(_model_path()), embedding=True,
                               n_ctx=2048, n_batch=256, verbose=False, **cpu)
        return _model


def _embed_impl(payload: dict) -> list[float]:
    """Worker-side executor — runs ONLY on the engine/inference.py owner
    thread (015 FR-001; same serialization rule as the chat model)."""
    result = _load().create_embedding(payload["text"][:MAX_EMBED_CHARS])
    vector = result["data"][0]["embedding"]
    if vector and isinstance(vector[0], list):  # per-token: mean-pool
        length = len(vector)
        vector = [sum(col) / length for col in zip(*vector)]
    return [float(v) for v in vector]


def embed(text: str) -> list[float] | None:
    """Embedding vector for text, or None on any failure (never raises).
    015 (FR-001): execution is serialized through the inference owner."""
    if not text or not available():
        return None
    from . import inference

    try:
        return inference.run_embed(text)
    except Exception:
        log.warning("embedding failed", exc_info=True)
        return None


def pack(vector: list[float]) -> bytes:
    return struct.pack(f"<{len(vector)}f", *vector)


def unpack(blob: bytes | None) -> list[float] | None:
    if not blob:
        return None
    if len(blob) % 4 != 0:
        return None
    try:
        return list(struct.unpack(f"<{len(blob) // 4}f", blob))
    except struct.error:
        return None


def cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if not norm_a or not norm_b:
        return 0.0
    return dot / (norm_a * norm_b)


def order_jobs(resume_vec: list[float] | None, jobs: list[dict]) -> list[dict]:
    """Jobs with vectors first, most-similar first; vectorless jobs keep
    their incoming (date) order behind them. No resume vector: unchanged."""
    if not resume_vec:
        return list(jobs)
    with_vec: list[tuple[float, dict]] = []
    without: list[dict] = []
    for job in jobs:
        vec = unpack(job.get("embedding"))
        if vec is not None and len(vec) == len(resume_vec):
            with_vec.append((cosine(resume_vec, vec), job))
        else:
            without.append(job)
    with_vec.sort(key=lambda pair: -pair[0])
    return [job for _, job in with_vec] + without


def selftest() -> str:
    """Diagnostics hook: a real embedding of a real string."""
    if not available():
        raise RuntimeError(f"embedding model missing at {_model_path()}")
    vector = embed("diagnostics self-test")
    if not vector:
        raise RuntimeError("model present but embedding failed — see app.log")
    return f"{len(vector)}-dim vector"
