"""008 US6 (T052): offline semantic pre-ranking — vector plumbing, ordering,
and graceful degradation. The real EmbeddingGemma model is never loaded in
unit tests; embed() is monkeypatched."""
import pytest

from engine import db, semantic
from tests.test_db import make_job


class TestVectorPlumbing:
    def test_pack_unpack_roundtrip(self):
        vec = [0.25, -1.5, 3.0]
        assert semantic.unpack(semantic.pack(vec)) == pytest.approx(vec)

    def test_unpack_garbage_returns_none(self):
        assert semantic.unpack(None) is None
        assert semantic.unpack(b"xyz") is None  # not a whole number of floats

    def test_cosine(self):
        assert semantic.cosine([1, 0], [1, 0]) == pytest.approx(1.0)
        assert semantic.cosine([1, 0], [0, 1]) == pytest.approx(0.0)
        assert semantic.cosine([1, 0], [-1, 0]) == pytest.approx(-1.0)
        assert semantic.cosine([0, 0], [1, 0]) == 0.0  # zero vector: no signal


class TestOrdering:
    def test_orders_by_similarity_with_vectorless_last(self):
        resume_vec = [1.0, 0.0]
        jobs = [
            {"id": 1, "embedding": semantic.pack([0.0, 1.0])},   # orthogonal
            {"id": 2, "embedding": semantic.pack([1.0, 0.1])},   # close
            {"id": 3, "embedding": None},                         # no vector
            {"id": 4, "embedding": semantic.pack([0.7, 0.7])},   # middling
        ]
        ordered = [j["id"] for j in semantic.order_jobs(resume_vec, jobs)]
        assert ordered == [2, 4, 1, 3]

    def test_no_resume_vector_keeps_original_order(self):
        jobs = [{"id": 1, "embedding": None}, {"id": 2, "embedding": None}]
        assert [j["id"] for j in semantic.order_jobs(None, jobs)] == [1, 2]


class TestPipelineIntegration:
    """020 RELOCATION: embedding moved out of the refresh and into the
    background AI assessment pass (engine/upgrade.py).

    008 put embedding in the scoring stage because that stage chose which jobs
    to spend the AI quota on. In 020 that choice belongs to the assessment
    pass, and embedding costs 0.60 s a job with a 300-job cap — three minutes
    of inference that has no business inside a refresh which now promises to
    finish in seconds. The BEHAVIOUR asserted here is unchanged; only its
    owner moved, so these tests now drive upgrade.run_once().
    """

    def test_new_jobs_get_embeddings_and_assessment_goes_top_down(
        self, tmp_db, monkeypatch
    ):
        from engine import matcher, upgrade

        db.save_profile(resume_text="fpga verification resume", skills=["fpga"])
        db.upsert_job(make_job(url="https://x/match", title="FPGA Engineer"))
        db.upsert_job(make_job(url="https://x/off", title="Bakery Manager"))
        with db._conn() as conn:
            conn.execute("UPDATE jobs SET is_entry_level = 1")

        def fake_embed(text):
            return [1.0, 0.0] if "fpga" in text.lower() else [0.0, 1.0]

        # a local tier must EXIST for a pass to happen at all, but no real
        # model may be touched — the assessor is stubbed below
        monkeypatch.delenv("LLM_API_KEY", raising=False)
        monkeypatch.setattr(matcher.local_llm, "available", lambda: True)
        monkeypatch.setattr(semantic, "available", lambda: True)
        monkeypatch.setattr(semantic, "embed", fake_embed)

        assessed_order = []

        def fake_analyze(_resume, title, _company, _description):
            assessed_order.append(title)
            return matcher.MatchAnalysis(match_score=70, reasoning="assessed")

        monkeypatch.setattr(matcher, "analyze_match", fake_analyze)
        upgrade.run_once(limit=2)

        with db._conn() as conn:
            rows = conn.execute(
                "SELECT title, embedding FROM jobs ORDER BY id"
            ).fetchall()
        assert all(row["embedding"] is not None for row in rows)
        assert assessed_order[0] == "FPGA Engineer"  # top-ranked assessed first
        profile = db.get_profile()
        assert profile["resume_embedding"] is not None

    def test_missing_model_degrades_silently(self, tmp_db, monkeypatch):
        """Unchanged guarantee: no embedding model means the incoming order,
        never a crash — and the jobs still carry scores, which after 020 the
        REFRESH already guaranteed before any pass runs."""
        from engine import matcher, pipeline, upgrade

        db.save_profile(resume_text="some resume")
        db.upsert_job(make_job(url="https://x/1", title="Role"))
        with db._conn() as conn:
            conn.execute("UPDATE jobs SET is_entry_level = 1")
        monkeypatch.setattr(semantic, "available", lambda: False)
        monkeypatch.delenv("LLM_API_KEY", raising=False)
        monkeypatch.setattr(matcher.local_llm, "available", lambda: True)
        monkeypatch.setattr(matcher, "analyze_match", lambda *a:
                            matcher.MatchAnalysis(match_score=70, reasoning="a"))

        pipeline._rank_new_jobs()
        upgrade.run_once(limit=5)  # must not raise

        jobs, _ = db.query_jobs(window=None, statuses=None, entry_level=None)
        assert jobs[0]["match_score"] is not None

    def test_the_refresh_itself_never_embeds(self, tmp_db, monkeypatch):
        """The relocation, pinned. Embedding inside the run would put three
        minutes of inference back into a refresh that promises seconds."""
        from engine import pipeline

        db.save_profile(resume_text="fpga resume")
        db.upsert_job(make_job(url="https://x/1", title="Role"))
        with db._conn() as conn:
            conn.execute("UPDATE jobs SET is_entry_level = 1")

        monkeypatch.setattr(semantic, "available", lambda: True)
        monkeypatch.setattr(semantic, "embed", lambda text: (
            _ for _ in ()).throw(AssertionError("the refresh must not embed")))

        pipeline._rank_new_jobs()

        jobs, _ = db.query_jobs(window=None, statuses=None, entry_level=None)
        assert jobs[0]["match_score"] is not None


class TestLoadHygiene016:
    """016 (T020, R13): a failing 330 MB embedder load is attempted ONCE
    per session, and the scores buffer is capped via n_batch."""

    def test_load_failure_never_retries(self, monkeypatch):
        import sys
        import types

        calls = []

        class BoomLlama:
            def __init__(self, *args, **kwargs):
                calls.append(1)
                raise RuntimeError("corrupt gguf")

        monkeypatch.setitem(sys.modules, "llama_cpp",
                            types.SimpleNamespace(Llama=BoomLlama))
        monkeypatch.setattr(semantic, "_model", None)
        monkeypatch.setattr(semantic, "_load_attempted", False)
        with pytest.raises(Exception):
            semantic._load()
        first_round = len(calls)
        assert first_round >= 1
        with pytest.raises(Exception):
            semantic._load()
        assert len(calls) == first_round  # no re-attempt

    def test_embedder_caps_n_batch(self, monkeypatch):
        import sys
        import types

        seen = {}

        class FakeLlama:
            def __init__(self, *args, **kwargs):
                seen.update(kwargs)

        monkeypatch.setitem(sys.modules, "llama_cpp",
                            types.SimpleNamespace(Llama=FakeLlama))
        monkeypatch.setattr(semantic, "_model", None)
        monkeypatch.setattr(semantic, "_load_attempted", False)
        semantic._load()
        assert seen.get("n_batch") == 256
