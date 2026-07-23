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


def _load():
    global _model
    with _lock:
        if _model is None:
            from llama_cpp import Llama

            _model = Llama(
                model_path=str(_model_path()),
                embedding=True,
                n_ctx=2048,
                verbose=False,
            )
        return _model


def embed(text: str) -> list[float] | None:
    """Embedding vector for text, or None on any failure (never raises)."""
    if not text or not available():
        return None
    try:
        result = _load().create_embedding(text[:MAX_EMBED_CHARS])
        vector = result["data"][0]["embedding"]
        if vector and isinstance(vector[0], list):  # per-token: mean-pool
            length = len(vector)
            vector = [sum(col) / length for col in zip(*vector)]
        return [float(v) for v in vector]
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
