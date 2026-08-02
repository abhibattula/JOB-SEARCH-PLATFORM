"""T013: refresh orchestration — per-source isolation, run records, cooldown."""
import pytest

from engine import db, pipeline
from engine.ingest.base import RawJob


def fake_source(name, jobs=None, error=None):
    class Module:
        SOURCE_NAME = name

        @staticmethod
        def fetch_jobs(entries):
            if error:
                raise error
            return jobs or []

    return Module


def raw(title, url, source):
    return RawJob(title=title, company="TestCo", url=url, source=source)


@pytest.fixture()
def fake_sources(monkeypatch, tmp_db):
    good = fake_source(
        "good",
        jobs=[raw("Engineer A", "https://x.example/a", "good"),
              raw("Engineer B", "https://x.example/b", "good")],
    )
    bad = fake_source("bad", error=RuntimeError("boom"))
    modules = {"good": good, "bad": bad}
    monkeypatch.setattr(pipeline, "_source_names", lambda: ["good", "bad"])
    monkeypatch.setattr(pipeline, "_get_source", lambda name: modules[name])
    monkeypatch.setattr(pipeline, "load_companies", lambda: [])
    return modules


class TestRunRefresh:
    def test_failure_isolated_and_run_recorded(self, fake_sources):
        summary = pipeline.run_refresh(trigger="cli")
        assert summary["started"] is True
        assert summary["sources"]["good"]["state"] == "done"
        assert summary["sources"]["good"]["added"] == 2
        assert summary["sources"]["bad"]["state"] == "failed"
        assert "boom" in summary["sources"]["bad"]["error"]
        _, total = db.query_jobs(window=None)
        assert total == 2
        assert db.get_run_status()["active"] is False

    def test_cooldown_blocks_second_run(self, fake_sources):
        assert pipeline.run_refresh(trigger="auto")["started"] is True
        blocked = pipeline.run_refresh(trigger="auto")
        assert blocked["started"] is False
        assert blocked["reason"] == "cooldown"

    def test_force_bypasses_cooldown(self, fake_sources):
        pipeline.run_refresh(trigger="auto")
        forced = pipeline.run_refresh(trigger="manual", force=True)
        assert forced["started"] is True


class TestScoringStage:
    @pytest.fixture()
    def entry_source(self, monkeypatch, tmp_db):
        source = fake_source(
            "good",
            jobs=[
                raw("Software Engineer, New Grad", "https://x.example/ng", "good"),
                raw("Senior Software Engineer", "https://x.example/sr", "good"),
            ],
        )
        monkeypatch.setattr(pipeline, "_source_names", lambda: ["good"])
        monkeypatch.setattr(pipeline, "_get_source", lambda name: source)
        monkeypatch.setattr(pipeline, "load_companies", lambda: [])
        db.save_profile(resume_text="my resume", resume_filename="r.pdf")
        return source

    def test_entry_level_jobs_scored_when_resume_present(self, entry_source,
                                                         monkeypatch):
        """020 PROMISE CHANGE (FR-001): the refresh no longer produces an AI
        score. It produces a keyword score for EVERY eligible job, and the AI
        assessment happens afterwards in engine/upgrade.py.

        Before 020 this asserted `match_score == 81` — the value a stubbed
        assessor returned inline. That inline call is what held the run open
        for hours; see specs/020-every-job-ranked/research.md R2. The
        assessment half of this journey is covered by TestRunLifecycle020.
        """
        monkeypatch.setenv("LLM_API_KEY", "test")
        monkeypatch.setattr(
            pipeline, "_analyze",
            lambda *a: (_ for _ in ()).throw(
                AssertionError("the refresh must not assess with the model")))
        pipeline.run_refresh(trigger="cli")
        jobs, _ = db.query_jobs(window=None, statuses=None, entry_level=True)
        assert len(jobs) == 1  # senior job excluded by classifier
        assert jobs[0]["match_score"] is not None
        assert jobs[0]["match_method"] == "basic"

    def test_assessment_failure_still_leaves_a_ranked_job(self, entry_source,
                                                          monkeypatch):
        """020 PROMISE INVERSION (FR-002). This test previously asserted the
        OPPOSITE — that a failed analysis leaves `match_score is None`.

        That behaviour is the defect this feature exists to remove: on the
        applicant's database it left 627 of 937 eligible jobs unscored and
        therefore invisible to the score filter. A job may now be scored
        approximately, but it is never left unranked because inference failed.
        """
        monkeypatch.setenv("LLM_API_KEY", "test")
        monkeypatch.setattr(pipeline, "_analyze", lambda *a: None)
        pipeline.run_refresh(trigger="cli")
        jobs, _ = db.query_jobs(window=None, statuses=None, entry_level=True)
        assert len(jobs) == 1
        assert jobs[0]["match_score"] is not None
        assert jobs[0]["match_method"] == "basic"

    def test_no_key_falls_back_to_basic_scoring(self, entry_source, monkeypatch):
        """005: neither cloud key nor local model available -> basic tier."""
        from engine import matcher

        monkeypatch.delenv("LLM_API_KEY", raising=False)
        monkeypatch.setattr(matcher.local_llm, "available", lambda: False)
        monkeypatch.setattr(
            pipeline, "_analyze",
            lambda *a: (_ for _ in ()).throw(AssertionError("LLM must not be called")),
        )
        pipeline.run_refresh(trigger="cli")
        jobs, _ = db.query_jobs(window=None, statuses=None, entry_level=True)
        assert len(jobs) == 1
        assert jobs[0]["match_score"] is not None
        assert jobs[0]["match_method"] == "basic"

    def test_basic_scoring_passes_profile_skills_as_extra_skills(self, entry_source, monkeypatch):
        """006-E: the user's explicit Profile skills list feeds into basic
        scoring alongside whatever the resume-text regex extraction finds."""
        from engine import basic_match, matcher

        monkeypatch.delenv("LLM_API_KEY", raising=False)
        monkeypatch.setattr(matcher.local_llm, "available", lambda: False)
        db.save_profile(skills=["i2c", "rust"])
        calls = []

        def fake_score(resume_text, title, description, extra_skills=None):
            calls.append(extra_skills)
            return matcher.MatchAnalysis(match_score=50, reasoning="basic")

        monkeypatch.setattr(basic_match, "score", fake_score)
        pipeline.run_refresh(trigger="cli")

        assert len(calls) == 1
        assert calls[0] == {"i2c", "rust"}

    def test_the_refresh_ranks_the_same_way_whatever_tier_is_available(
            self, entry_source, monkeypatch):
        """020 PROMISE CHANGE. Before 020 this was 005-T015: with the local
        model present the refresh scored inline and tagged method='local'.

        The tier no longer influences the refresh at all — that is the point.
        Ranking is deterministic and identical whether a cloud key exists, the
        bundled model exists, or neither does, so the feed can never again be
        left partly unscored because a tier was slow or missing. Which tier
        performs the later ASSESSMENT is still tested, in test_upgrade.py.
        """
        from engine import matcher

        monkeypatch.setattr(pipeline, "_analyze", lambda *a: (_ for _ in ()).throw(
            AssertionError("the refresh must not assess with the model")))
        pipeline.run_refresh(trigger="cli")  # ingest + classify + rank

        scores = {}
        for label, key, model in (("local", False, True),
                                  ("cloud", True, False),
                                  ("neither", False, False)):
            with monkeypatch.context() as ctx:
                if key:
                    ctx.setenv("LLM_API_KEY", "test")
                else:
                    ctx.delenv("LLM_API_KEY", raising=False)
                ctx.setattr(matcher.local_llm, "available", lambda: model)
                ctx.setattr(pipeline, "_analyze", lambda *a: (_ for _ in ()).throw(
                    AssertionError("the refresh must not assess with the model")))
                # re-rank from scratch each time
                with db._conn() as conn:
                    conn.execute("UPDATE jobs SET match_score = NULL,"
                                 " match_json = NULL")
                pipeline._rank_new_jobs()
            jobs, _ = db.query_jobs(window=None, statuses=None, entry_level=True)
            assert len(jobs) == 1
            assert jobs[0]["match_method"] == "basic", label
            scores[label] = jobs[0]["match_score"]

        assert len(set(scores.values())) == 1, scores


class TestRanking020:
    """020 US1 (FR-001, FR-002): every eligible job gets a score during the
    refresh that ingests it, from the deterministic keyword matcher, with no
    cap and without touching the model.

    This replaces the pre-020 behaviour where a single tier scored a capped
    slice per run. On the applicant's own database that left 627 of 937
    eligible jobs permanently unscored, because the AI tier costs ~67 s a job
    and the run was superseded long before it finished (baseline.txt).
    """

    @pytest.fixture()
    def many_entry_jobs(self, monkeypatch, tmp_db):
        from engine import matcher

        jobs = [raw(f"Software Engineer, New Grad {i}",
                    f"https://x.example/ng{i}", "good") for i in range(25)]
        source = fake_source("good", jobs=jobs)
        monkeypatch.setattr(pipeline, "_source_names", lambda: ["good"])
        monkeypatch.setattr(pipeline, "_get_source", lambda name: source)
        monkeypatch.setattr(pipeline, "load_companies", lambda: [])
        # The bundled GGUF models are present in a dev checkout, so
        # matcher.scoring_tier() resolves to "local" here and the pre-020 code
        # under test would run REAL inference — 25 jobs x ~67 s. Stub the
        # assessor so these tests measure ranking, never the model. Tests that
        # care about the assessor's behaviour override this.
        monkeypatch.setattr(
            pipeline, "_analyze",
            lambda *a: matcher.MatchAnalysis(match_score=77,
                                             reasoning="stub assessment"))
        db.save_profile(resume_text="python c++ fpga embedded rtos",
                        resume_filename="r.pdf")
        return source

    @staticmethod
    def _eligible_unscored() -> int:
        with db._conn() as conn:
            return conn.execute(
                "SELECT COUNT(*) FROM jobs WHERE match_score IS NULL"
                " AND delisted = 0 AND is_entry_level = 1"
                " AND sponsorship != 'EXCLUDED'").fetchone()[0]

    def test_every_eligible_job_is_ranked_with_no_cap(self, many_entry_jobs,
                                                      monkeypatch):
        """FR-001. The cap that used to apply here is now the AI-assessment
        cap and must not limit ranking."""
        monkeypatch.setattr(db, "set_setting", db.set_setting)
        db.set_setting("MAX_SCORE_PER_RUN", "5")
        pipeline.run_refresh(trigger="cli")
        assert self._eligible_unscored() == 0

    def test_ranking_never_touches_the_model(self, many_entry_jobs, monkeypatch):
        """FR-002 / guarantee R2 — the whole point. If inference is down,
        broken, or simply slow, the feed must still be fully ranked."""
        from engine import local_llm, matcher

        def explode(*_a, **_k):
            raise AssertionError("ranking must never call the model")

        monkeypatch.setattr(matcher, "_chat", explode)
        monkeypatch.setattr(matcher, "analyze_match", explode)
        monkeypatch.setattr(local_llm, "chat", explode)
        monkeypatch.setattr(pipeline, "_analyze", explode)

        pipeline.run_refresh(trigger="cli")
        assert self._eligible_unscored() == 0

    def test_ranked_jobs_are_tagged_basic(self, many_entry_jobs):
        pipeline.run_refresh(trigger="cli")
        jobs, _ = db.query_jobs(window=None, statuses=None, entry_level=True)
        assert jobs
        assert {j["match_method"] for j in jobs} == {"basic"}

    def test_ranking_does_not_overwrite_an_existing_score(self, many_entry_jobs):
        """Guarantee R3 — an AI-assessed job must never be knocked back down
        to a keyword score by the next refresh."""
        import json

        pipeline.run_refresh(trigger="cli")
        jobs, _ = db.query_jobs(window=None, statuses=None, entry_level=True)
        target = jobs[0]["id"]
        db.set_match(target, 93.0, json.dumps(
            {"match_score": 93.0, "reasoning": "assessed", "method": "local"}))

        pipeline.run_refresh(trigger="cli", force=True)

        after = db.get_job(target)
        assert after["match_score"] == 93.0
        assert json.loads(after["match_json"])["method"] == "local"

    def test_profile_skills_reach_the_matcher(self, many_entry_jobs, monkeypatch):
        """Guarantee R4 — 006-E's behaviour survives the tier split."""
        from engine import basic_match, matcher

        db.save_profile(skills=["i2c", "rust"])
        seen = []

        def fake_score(resume_text, title, description, extra_skills=None):
            seen.append(extra_skills)
            return matcher.MatchAnalysis(match_score=50, reasoning="basic")

        monkeypatch.setattr(basic_match, "score", fake_score)
        pipeline.run_refresh(trigger="cli")

        assert seen, "basic_match.score was never called"
        assert all(s == {"i2c", "rust"} for s in seen)

    def test_a_job_with_no_description_is_still_ranked(self, monkeypatch, tmp_db):
        """Edge case from the spec: an empty description must not drop a job
        back into the unranked pool."""
        source = fake_source("good", jobs=[
            raw("Software Engineer, New Grad", "https://x.example/empty", "good")])
        monkeypatch.setattr(pipeline, "_source_names", lambda: ["good"])
        monkeypatch.setattr(pipeline, "_get_source", lambda name: source)
        monkeypatch.setattr(pipeline, "load_companies", lambda: [])
        db.save_profile(resume_text="python", resume_filename="r.pdf")

        pipeline.run_refresh(trigger="cli")
        assert self._eligible_unscored() == 0

    def test_no_resume_means_no_ranking_and_no_crash(self, many_entry_jobs,
                                                     tmp_db):
        """Unchanged pre-020 behaviour: without a resume there is nothing to
        match against, and the refresh must still succeed."""
        db.save_profile(resume_text="")
        summary = pipeline.run_refresh(trigger="cli")
        assert summary["started"] is True


class TestRankingThroughput020:
    """020 SC-002: ranking the applicant's entire eligible backlog finishes in
    well under 30 seconds without any inference.

    627 jobs is the exact size of the backlog this feature was written for
    (specs/020-every-job-ranked/baseline.txt). At the pre-020 local tier's
    measured 66.8 s a job the same work was 11.6 hours.
    """

    BACKLOG = 627
    BUDGET_S = 30.0

    @staticmethod
    def _seed(count: int, description: str = "python") -> None:
        """Insert `count` ELIGIBLE unscored jobs.

        db.upsert_job returns a status string ("inserted"), NOT a row id — a
        first draft of this test passed it straight to set_classification, so
        nothing was ever marked entry-level, the eligible set was empty, and
        `unscored == 0` held vacuously while 627 jobs "ranked" in 0.00 s.
        Seeding goes through a helper now, and every caller asserts the
        backlog exists before ranking it.
        """
        for i in range(count):
            url = f"https://x.example/backlog/{i}"
            db.upsert_job({
                "title": f"Software Engineer, New Grad {i}",
                "company": f"Company {i}",
                "url": url,
                "source": "greenhouse",
                "location": "Remote",
                "is_remote": True,
                "description": description,
                "posted_date": "2026-07-30",
            })
        with db._conn() as conn:
            conn.execute(
                "UPDATE jobs SET is_entry_level = 1, sponsorship = 'UNKNOWN',"
                " delisted = 0")

    @staticmethod
    def _eligible_unscored() -> int:
        with db._conn() as conn:
            return conn.execute(
                "SELECT COUNT(*) FROM jobs WHERE match_score IS NULL"
                " AND delisted = 0 AND is_entry_level = 1"
                " AND sponsorship != 'EXCLUDED'").fetchone()[0]

    def test_the_whole_backlog_ranks_inside_the_budget(self, tmp_db, monkeypatch):
        import time

        from engine import local_llm, matcher

        db.save_profile(
            resume_text="python c++ verilog fpga embedded rtos git linux",
            resume_filename="r.pdf", skills=["python", "c++"])

        self._seed(self.BACKLOG,
                   ("Entry level embedded firmware role. C++, Python, "
                    "debugging, hardware bring-up. BS in CE/EE/CS. ") * 8)

        # the guard whose absence made the first version of this test a lie
        assert self._eligible_unscored() == self.BACKLOG, (
            "the backlog was not seeded; the timing below would be meaningless")

        def explode(*_a, **_k):
            raise AssertionError("ranking must never call the model")

        monkeypatch.setattr(matcher, "analyze_match", explode)
        monkeypatch.setattr(local_llm, "chat", explode)
        monkeypatch.setattr(pipeline, "_analyze", explode)

        started = time.monotonic()
        pipeline._rank_new_jobs()
        elapsed = time.monotonic() - started

        assert self._eligible_unscored() == 0
        assert elapsed < self.BUDGET_S, (
            f"ranked {self.BACKLOG} jobs in {elapsed:.1f}s, "
            f"budget {self.BUDGET_S}s")
        print(f"\n  ranked {self.BACKLOG} jobs in {elapsed:.2f}s "
              f"({elapsed / self.BACKLOG * 1000:.2f} ms/job)")

    def test_every_ranked_job_really_carries_a_basic_score(self, tmp_db):
        """The companion assertion to the timing one: prove work was DONE, not
        merely that no unscored rows remain."""
        db.save_profile(resume_text="python c++", resume_filename="r.pdf")
        self._seed(20)
        assert self._eligible_unscored() == 20

        pipeline._rank_new_jobs()

        jobs, total = db.query_jobs(window=None, statuses=None, entry_level=True)
        assert total == 20
        assert all(j["match_score"] is not None for j in jobs)
        assert {j["match_method"] for j in jobs} == {"basic"}

    def test_ranking_reads_the_backlog_in_chunks(self, tmp_db, monkeypatch):
        """A backlog far larger than one chunk must still fully rank — the
        loop has to keep fetching, and must stop rather than spin when a chunk
        makes no progress."""
        monkeypatch.setattr(pipeline, "_RANK_BATCH", 10)
        db.save_profile(resume_text="python", resume_filename="r.pdf")
        self._seed(35)
        assert self._eligible_unscored() == 35

        pipeline._rank_new_jobs()

        assert self._eligible_unscored() == 0

    def test_a_matcher_that_always_fails_terminates(self, tmp_db, monkeypatch):
        """The no-progress guard. Without it the loop refetches the same
        unscored rows forever and the refresh never returns."""
        from engine import basic_match

        db.save_profile(resume_text="python", resume_filename="r.pdf")
        self._seed(3)
        assert self._eligible_unscored() == 3

        def boom(*_a, **_k):
            raise ValueError("unrankable")

        monkeypatch.setattr(basic_match, "score", boom)
        pipeline._rank_new_jobs()  # must return, not hang

        # and it genuinely could not rank them — proving the guard was hit
        assert self._eligible_unscored() == 3
