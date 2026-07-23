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
    def test_new_jobs_get_embeddings_and_scoring_goes_top_down(
        self, tmp_db, monkeypatch
    ):
        from engine import pipeline

        db.save_profile(resume_text="fpga verification resume", skills=["fpga"])
        db.upsert_job(make_job(url="https://x/match", title="FPGA Engineer"))
        db.upsert_job(make_job(url="https://x/off", title="Bakery Manager"))
        with db._conn() as conn:
            conn.execute("UPDATE jobs SET is_entry_level = 1")

        def fake_embed(text):
            return [1.0, 0.0] if "fpga" in text.lower() else [0.0, 1.0]

        # force the basic tier: a dev machine's models/ gguf would otherwise
        # run REAL local inference here
        from engine import matcher

        monkeypatch.delenv("LLM_API_KEY", raising=False)
        monkeypatch.setattr(matcher.local_llm, "available", lambda: False)
        monkeypatch.setattr(semantic, "available", lambda: True)
        monkeypatch.setattr(semantic, "embed", fake_embed)
        scored_order = []
        from engine import basic_match

        real_score = basic_match.score  # capture BEFORE patching

        def fake_score(resume_text, title, description, extra_skills=None):
            scored_order.append(title)
            return real_score(resume_text, title, description, extra_skills=extra_skills)

        monkeypatch.setattr(basic_match, "score", fake_score)
        pipeline._score_new_jobs()

        with db._conn() as conn:
            rows = conn.execute(
                "SELECT title, embedding FROM jobs ORDER BY id"
            ).fetchall()
        assert all(row["embedding"] is not None for row in rows)
        assert scored_order[0] == "FPGA Engineer"  # top-ranked scored first
        profile = db.get_profile()
        assert profile["resume_embedding"] is not None

    def test_missing_model_degrades_silently(self, tmp_db, monkeypatch):
        from engine import pipeline

        db.save_profile(resume_text="some resume")
        db.upsert_job(make_job(url="https://x/1", title="Role"))
        with db._conn() as conn:
            conn.execute("UPDATE jobs SET is_entry_level = 1")
        monkeypatch.setattr(semantic, "available", lambda: False)
        from engine import matcher

        monkeypatch.delenv("LLM_API_KEY", raising=False)
        monkeypatch.setattr(matcher.local_llm, "available", lambda: False)
        pipeline._score_new_jobs()  # must not raise; jobs still get scored
        jobs, _ = db.query_jobs(window=None, statuses=None, entry_level=None)
        assert jobs[0]["match_score"] is not None
