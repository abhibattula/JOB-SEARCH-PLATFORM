"""020 (US2/US3): the background AI assessment pass.

engine/upgrade.py promotes quick-scored ("basic") jobs to full AI assessment,
one at a time, best-first by semantic similarity, yielding entirely to an
active application fill session. It is the half of scoring that costs ~67 s a
job on the applicant's laptop, so it lives OUTSIDE the refresh run — the
inline version held that run open for 2 h 47 m and got superseded before it
could finish (research R2).

No real model is ever loaded here; every test stubs the assessor.
"""
from __future__ import annotations

import threading
import time

import pytest

from engine import upgrade


@pytest.fixture(autouse=True)
def _fresh_upgrade():
    upgrade.reset_for_tests()
    yield
    upgrade.reset_for_tests()


class TestProgressShape020:
    """T003 (FR-011): the read-only projection the status endpoint renders.

    It has to answer safely before anything has ever run — the feed asks on
    every page load, including the very first one after install.
    """

    _KEYS = {"running", "done", "total", "failed", "paused_for_session"}

    def test_defaults_before_any_pass(self):
        snap = upgrade.progress()
        assert set(snap) == self._KEYS
        assert snap == {"running": False, "done": 0, "total": 0,
                        "failed": 0, "paused_for_session": False}

    def test_shape_is_always_complete(self):
        """Never a partial dict — the template reads every key unconditionally,
        so a missing one is a 500 on the feed rather than a blank badge."""
        for key, kind in (("running", bool), ("done", int), ("total", int),
                          ("failed", int), ("paused_for_session", bool)):
            assert isinstance(upgrade.progress()[key], kind), key

    def test_snapshot_is_a_copy(self):
        """A caller mutating what it got back must not corrupt pass state."""
        snap = upgrade.progress()
        snap["done"] = 999
        assert upgrade.progress()["done"] == 0

    def test_safe_from_any_thread_and_does_not_block(self):
        """The status endpoint calls this while a pass may be mid-assessment;
        it must never wait on the pass (contracts/upgrade-api.md)."""
        seen: list[dict] = []
        errors: list[BaseException] = []

        def read():
            try:
                for _ in range(50):
                    seen.append(upgrade.progress())
            except BaseException as exc:  # noqa: BLE001 — surface it
                errors.append(exc)

        threads = [threading.Thread(target=read) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5)
            assert not t.is_alive(), "progress() blocked a reader"
        assert not errors
        assert len(seen) == 200
        assert all(set(s) == self._KEYS for s in seen)

    def test_reset_restores_defaults(self):
        upgrade.reset_for_tests()
        assert upgrade.progress() == {"running": False, "done": 0, "total": 0,
                                      "failed": 0, "paused_for_session": False}


def _imported_modules(module) -> set[str]:
    """Every module name this module imports, including inside functions.

    Parsed from the AST, not grepped from the source: a substring search
    matches the module's own docstring prose ("imports nothing from web/") and
    would pass or fail for reasons that have nothing to do with the imports.
    """
    import ast
    import inspect

    names: set[str] = set()
    for node in ast.walk(ast.parse(inspect.getsource(module))):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                names.add(node.module)
            # `from . import db` — the module IS the alias, and node.module is
            # None. This codebase imports that way almost everywhere, so
            # reading node.module alone would see nothing at all.
            names.update(alias.name for alias in node.names)
    return names


class TestModuleBoundaries020:
    """Principle IV + guarantee L5. Cheap to assert, and the exact mistake
    that would make this module unusable from the CLI."""

    def test_does_not_import_web(self):
        imported = _imported_modules(upgrade)
        assert not any(name == "web" or name.startswith("web.")
                       for name in imported), imported

    def test_does_not_import_pipeline(self):
        """pipeline imports upgrade; the dependency runs ONE way only. A cycle
        here would break `from engine import pipeline` at import time."""
        imported = _imported_modules(upgrade)
        assert not any(name.split(".")[-1] == "pipeline"
                       for name in imported), imported

    def test_the_boundary_check_can_actually_fail(self):
        """The 019 lesson: never let an assertion pass for a reason unrelated
        to what it claims. Plant both forbidden imports — in the two shapes
        this codebase actually writes — and prove the detector sees them.

        This caught a real bug when it was written: the first detector read
        only `node.module`, so `from . import pipeline` (module=None, the
        dominant style in engine/) was invisible to it.
        """
        import textwrap
        import types

        offender = types.ModuleType("offender")
        offender.__source__ = textwrap.dedent('''
            """A module whose docstring mentions web/ and pipeline harmlessly."""
            from web import main
            def f():
                from . import pipeline
        ''')

        import ast
        import inspect

        real_getsource = inspect.getsource
        try:
            inspect.getsource = lambda m: m.__source__
            found = _imported_modules(offender)
        finally:
            inspect.getsource = real_getsource

        assert "web" in found, found
        assert "pipeline" in found, found
        assert ast is not None  # import used above


# --------------------------------------------------------------------------
# helpers shared by the pass tests
# --------------------------------------------------------------------------

def _seed_ranked(count: int, *, description: str = "python c++") -> list[int]:
    """`count` eligible jobs already carrying a keyword score — exactly what a
    refresh leaves behind, and exactly what the pass exists to upgrade."""
    import json

    from engine import db

    for i in range(count):
        db.upsert_job({
            "title": f"Software Engineer, New Grad {i}", "company": f"Co {i}",
            "url": f"https://x.example/pass/{i}", "source": "greenhouse",
            "location": "Remote", "is_remote": True,
            "description": description, "posted_date": "2026-07-30",
        })
    with db._conn() as conn:
        conn.execute("UPDATE jobs SET is_entry_level = 1,"
                     " sponsorship = 'UNKNOWN', delisted = 0")
        rows = conn.execute("SELECT id FROM jobs ORDER BY id").fetchall()
    ids = []
    for row in rows:
        db.set_match(row["id"], 40.0, json.dumps(
            {"match_score": 40.0, "reasoning": "keyword", "method": "basic"}))
        ids.append(row["id"])
    return ids


def _assessor(monkeypatch, seen=None, score=80):
    """Stub matcher.analyze_match. NO test in this file may reach a real
    model: one assessment costs ~67 s."""
    from engine import matcher

    def fake(_resume, title, _company, _description):
        if seen is not None:
            seen.append(title)
        return matcher.MatchAnalysis(match_score=score, reasoning="assessed")

    monkeypatch.setattr(matcher, "analyze_match", fake)
    return seen


def _never_assess(monkeypatch):
    from engine import matcher

    def boom(*_a, **_k):
        raise AssertionError("the pass must not assess here")

    monkeypatch.setattr(matcher, "analyze_match", boom)


@pytest.fixture()
def ready(tmp_db, monkeypatch):
    """A database with a resume and an upgrade tier available — and no real
    model anywhere near it. Embedding is inference too, so it is off unless a
    test explicitly asks for it."""
    from engine import db, matcher, semantic

    db.save_profile(resume_text="python c++ fpga embedded",
                    resume_filename="r.pdf")
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.setattr(matcher.local_llm, "available", lambda: True)
    monkeypatch.setattr(semantic, "available", lambda: False)
    # The stand-down POLLS for a session to end (a short session should not
    # cost a whole pass). Tests want the give-up branch immediately rather
    # than a real five-minute wait; TestFairness020 covers the polling path
    # explicitly with a small budget of its own.
    monkeypatch.setattr(upgrade, "MAX_PAUSE_S", 0.0)
    monkeypatch.setattr(upgrade, "PAUSE_POLL_S", 0.01)
    return db


class TestPassSelection020:
    """T013 (FR-004, guarantee G1): who gets assessed, in what order."""

    def test_only_keyword_scored_jobs_are_candidates(self, ready, monkeypatch):
        import json

        ids = _seed_ranked(4)
        ready.set_match(ids[0], 91.0, json.dumps(
            {"match_score": 91.0, "reasoning": "done", "method": "local"}))

        seen = _assessor(monkeypatch, [])
        upgrade.run_once(limit=10)

        assert len(seen) == 3, seen

    def test_limit_bounds_the_pass(self, ready, monkeypatch):
        _seed_ranked(9)
        seen = _assessor(monkeypatch, [])

        result = upgrade.run_once(limit=4)

        assert len(seen) == 4
        assert result["total"] == 4
        assert result["done"] == 4

    def test_semantic_order_decides_which_jobs_are_assessed(self, ready,
                                                            monkeypatch):
        """FR-004: best-first by similarity to the resume, not by date. The
        stub reverses the incoming order so 'ordered' is distinguishable from
        'whatever the query happened to return'."""
        from engine import semantic

        _seed_ranked(5)
        # A resume vector must exist, or the pass fetches exactly `limit`
        # candidates and there is nothing for the ordering to choose FROM.
        monkeypatch.setattr(upgrade, "_embed_pending",
                            lambda *_a: [0.1, 0.2, 0.3])
        monkeypatch.setattr(semantic, "order_jobs",
                            lambda vec, jobs: list(reversed(jobs)))
        seen = _assessor(monkeypatch, [])

        upgrade.run_once(limit=2)

        assert seen == ["Software Engineer, New Grad 4",
                        "Software Engineer, New Grad 3"], seen

    def test_assessed_jobs_carry_the_tier_and_the_full_analysis(self, ready,
                                                                monkeypatch):
        """FR-005: analysis content is pre-computed for every assessed job —
        the job page never generates on demand."""
        import json

        from engine import matcher

        ids = _seed_ranked(1)
        monkeypatch.setattr(matcher, "analyze_match", lambda *a:
                            matcher.MatchAnalysis(
                                match_score=88, reasoning="because",
                                matching_skills=["python"],
                                missing_skills=["go"]))

        upgrade.run_once(limit=1)

        job = ready.get_job(ids[0])
        payload = json.loads(job["match_json"])
        assert job["match_score"] == 88
        assert payload["method"] == "local"
        assert payload["matching_skills"] == ["python"]
        assert payload["missing_skills"] == ["go"]
        assert payload["reasoning"] == "because"

    def test_a_cloud_key_tags_the_assessment_llm(self, ready, monkeypatch):
        import json

        from engine import matcher

        monkeypatch.setenv("LLM_API_KEY", "test")
        monkeypatch.setattr(matcher.local_llm, "available", lambda: False)
        ids = _seed_ranked(1)
        _assessor(monkeypatch)

        upgrade.run_once(limit=1)

        assert json.loads(ready.get_job(ids[0])["match_json"])["method"] == "llm"

    def test_nothing_to_upgrade_to_means_no_pass(self, tmp_db, monkeypatch):
        """No cloud key and no bundled model: there is no better tier, so the
        pass must not burn a single call."""
        from engine import db, matcher, semantic

        db.save_profile(resume_text="python", resume_filename="r.pdf")
        monkeypatch.delenv("LLM_API_KEY", raising=False)
        monkeypatch.setattr(matcher.local_llm, "available", lambda: False)
        monkeypatch.setattr(semantic, "available", lambda: False)
        _seed_ranked(3)
        _never_assess(monkeypatch)

        assert upgrade.run_once(limit=5)["total"] == 0

    def test_no_resume_means_no_pass(self, tmp_db, monkeypatch):
        from engine import matcher, semantic

        monkeypatch.setattr(matcher.local_llm, "available", lambda: True)
        monkeypatch.setattr(semantic, "available", lambda: False)
        _seed_ranked(2)
        _never_assess(monkeypatch)

        assert upgrade.run_once(limit=5)["total"] == 0


class TestSingleFlight020:
    """T014 (FR-009, SC-005) — the direct fix for the duplicate-loop defect
    that left the applicant's database stuck at 310 of 937 scored."""

    def test_start_while_running_is_a_no_op(self, ready, monkeypatch):
        import threading

        from engine import matcher

        # this test is specifically about the threaded start(), so it opts out
        # of the conftest switch that keeps every other test off that path
        monkeypatch.delenv("JOBS_DISABLE_UPGRADE", raising=False)

        _seed_ranked(3)
        entered = threading.Event()
        release = threading.Event()

        def slow(*_a):
            entered.set()
            release.wait(timeout=10)
            return matcher.MatchAnalysis(match_score=70, reasoning="slow")

        monkeypatch.setattr(matcher, "analyze_match", slow)

        assert upgrade.start("test") is True
        assert entered.wait(timeout=10), "the pass never started"

        before = upgrade.progress()
        assert upgrade.start("test") is False
        assert upgrade.start("test") is False
        assert upgrade.progress()["total"] == before["total"]

        release.set()
        upgrade.join_for_tests(timeout=15)
        assert upgrade.progress()["running"] is False

    def test_the_test_switch_can_actually_stop_a_pass(self, ready):
        """Proves the conftest guard works, so pipeline tests cannot silently
        run real inference."""
        import os

        _seed_ranked(2)
        assert os.environ.get("JOBS_DISABLE_UPGRADE") == "1"
        assert upgrade.start("test") is False
        assert upgrade.progress()["running"] is False

    def test_run_once_ignores_the_disable_switch(self, ready, monkeypatch):
        """Explicit is explicit — every pass test in this file depends on it."""
        _seed_ranked(1)
        _assessor(monkeypatch)
        assert upgrade.run_once(limit=1)["done"] == 1


class TestFailureIsolation020:
    """T015 (FR-012, guarantee G4)."""

    def test_a_failing_job_keeps_its_keyword_score(self, ready, monkeypatch):
        import json

        from engine import matcher

        ids = _seed_ranked(1)
        monkeypatch.setattr(matcher, "analyze_match", lambda *a: (
            _ for _ in ()).throw(RuntimeError("model down")))

        result = upgrade.run_once(limit=1)

        job = ready.get_job(ids[0])
        assert job["match_score"] == 40.0
        assert json.loads(job["match_json"])["method"] == "basic"
        assert result["failed"] == 1
        assert result["done"] == 1

    def test_a_failure_does_not_stop_the_pass(self, ready, monkeypatch):
        from engine import matcher

        _seed_ranked(4)
        calls = {"n": 0}

        def flaky(_r, _t, _c, _d):
            calls["n"] += 1
            if calls["n"] == 1:
                raise RuntimeError("first one fails")
            return matcher.MatchAnalysis(match_score=75, reasoning="ok")

        monkeypatch.setattr(matcher, "analyze_match", flaky)
        result = upgrade.run_once(limit=4)

        assert calls["n"] == 4
        assert result["failed"] == 1
        assert result["done"] == 4

    def test_a_none_result_counts_as_failure_not_a_score(self, ready,
                                                         monkeypatch):
        """matcher.analyze_match returns None when its own bounded retry gave
        up. That must never be written as a score."""
        import json

        from engine import matcher

        ids = _seed_ranked(1)
        monkeypatch.setattr(matcher, "analyze_match", lambda *a: None)

        result = upgrade.run_once(limit=1)

        assert json.loads(
            ready.get_job(ids[0])["match_json"])["method"] == "basic"
        assert result["failed"] == 1

    def test_no_second_retry_layer_inside_a_pass(self, ready, monkeypatch):
        """analyze_match already retries once internally; stacking another
        retry on a ~67 s call would double the worst case for no gain."""
        from engine import matcher

        _seed_ranked(1)
        calls = {"n": 0}

        def counting(*_a):
            calls["n"] += 1
            raise RuntimeError("down")

        monkeypatch.setattr(matcher, "analyze_match", counting)
        upgrade.run_once(limit=1)

        assert calls["n"] == 1


class TestResume020:
    """T016 (FR-010, guarantee G5)."""

    def test_a_second_pass_skips_what_the_first_assessed(self, ready,
                                                         monkeypatch):
        _seed_ranked(6)
        seen = _assessor(monkeypatch, [])

        upgrade.run_once(limit=2)
        first = list(seen)
        seen.clear()
        upgrade.run_once(limit=2)

        assert len(seen) == 2
        assert not (set(first) & set(seen)), "a job was assessed twice"

    def test_pass_state_is_not_persisted(self, ready, monkeypatch):
        """Interrupting is safe precisely because nothing is stored: the next
        pass rebuilds its candidates from the database."""
        _seed_ranked(3)
        _assessor(monkeypatch)
        upgrade.run_once(limit=1)

        upgrade.reset_for_tests()  # stands in for an app restart
        assert upgrade.progress()["done"] == 0

        seen = _assessor(monkeypatch, [])
        upgrade.run_once(limit=5)

        assert len(seen) == 2, "the assessed job should not be revisited"


class TestFairness020:
    """T028-T031 (US3, FR-013/FR-014/FR-015): applying always beats ranking.

    This is the regression the rest of feature 020 could most easily cause.
    Before 020 assessment only ran DURING a refresh; now it can run at any
    moment, including while the applicant is filling a form. Both kinds of
    work share one serialized on-device worker (engine/inference.py) — a
    strict-FIFO queue with NO priority ordering.
    """

    def test_one_request_at_a_time_never_a_batch(self, ready, monkeypatch):
        """T028 (FR-014, guarantee G2).

        Blocking on each result is what keeps an Apply Assist draft waiting
        behind at most ONE assessment (~67 s, inside its 180 s budget).
        Enqueuing the whole pass would put that draft behind ~45 minutes.
        """
        from engine import matcher

        _seed_ranked(5)
        outstanding = {"now": 0, "max": 0}

        def tracked(*_a):
            outstanding["now"] += 1
            outstanding["max"] = max(outstanding["max"], outstanding["now"])
            try:
                return matcher.MatchAnalysis(match_score=80, reasoning="a")
            finally:
                outstanding["now"] -= 1

        monkeypatch.setattr(matcher, "analyze_match", tracked)
        upgrade.run_once(limit=5)

        assert outstanding["max"] == 1, outstanding

    def test_the_pass_stands_down_while_a_fill_session_is_live(self, ready,
                                                               monkeypatch):
        """T029 (FR-013, guarantee G3)."""
        from engine import matcher
        from engine.autofill import browser_controller as bc

        _seed_ranked(4)
        monkeypatch.setattr(bc, "session_is_live", lambda: True)
        _never_assess(monkeypatch)

        result = upgrade.run_once(limit=4)

        assert result["done"] == 0
        assert result["paused_for_session"] is True
        assert matcher is not None

    def test_it_resumes_once_the_session_ends(self, ready, monkeypatch):
        """Standing down must not mean giving up."""
        from engine.autofill import browser_controller as bc

        _seed_ranked(3)
        live = {"value": True}
        monkeypatch.setattr(bc, "session_is_live", lambda: live["value"])
        seen = _assessor(monkeypatch, [])

        assert upgrade.run_once(limit=3)["done"] == 0

        live["value"] = False
        assert upgrade.run_once(limit=3)["done"] == 3
        assert len(seen) == 3

    def test_a_session_starting_mid_pass_stops_further_assessment(
            self, ready, monkeypatch):
        """The check is per JOB, not once per pass — a session that starts
        after the pass began must still be respected."""
        from engine import matcher
        from engine.autofill import browser_controller as bc

        _seed_ranked(5)
        live = {"value": False}
        monkeypatch.setattr(bc, "session_is_live", lambda: live["value"])
        seen = []

        def assess_then_interrupt(_r, title, _c, _d):
            seen.append(title)
            if len(seen) == 2:
                live["value"] = True  # the applicant opened an application
            return matcher.MatchAnalysis(match_score=80, reasoning="a")

        monkeypatch.setattr(matcher, "analyze_match", assess_then_interrupt)
        result = upgrade.run_once(limit=5)

        assert len(seen) == 2, seen
        assert result["paused_for_session"] is True

    def test_embedding_stands_down_too(self, ready, monkeypatch):
        """Embedding is inference: 0.60 s a job, up to 300 a pass, through the
        same single worker as a draft. Guarding only the assessment loop would
        leave three minutes of model time ignoring a live fill session."""
        from engine import semantic
        from engine.autofill import browser_controller as bc

        _seed_ranked(3)
        monkeypatch.setattr(bc, "session_is_live", lambda: True)
        monkeypatch.setattr(semantic, "available", lambda: True)
        monkeypatch.setattr(semantic, "embed", lambda text: (
            _ for _ in ()).throw(AssertionError("must not embed while filling")))
        _never_assess(monkeypatch)

        result = upgrade.run_once(limit=3)

        assert result["done"] == 0
        assert result["paused_for_session"] is True

    def test_it_waits_for_a_short_session_rather_than_abandoning_the_pass(
            self, ready, monkeypatch):
        """The polling branch. A session that ends quickly — open a form, fill
        it, submit — should cost the pass a pause, not the whole pass."""
        import threading

        from engine.autofill import browser_controller as bc

        _seed_ranked(2)
        monkeypatch.setattr(upgrade, "MAX_PAUSE_S", 5.0)
        monkeypatch.setattr(upgrade, "PAUSE_POLL_S", 0.02)

        live = {"value": True}
        monkeypatch.setattr(bc, "session_is_live", lambda: live["value"])
        seen = _assessor(monkeypatch, [])

        threading.Timer(0.15, lambda: live.__setitem__("value", False)).start()
        result = upgrade.run_once(limit=2)

        assert result["done"] == 2, "the pass gave up on a short session"
        assert len(seen) == 2
        assert result["paused_for_session"] is False

    def test_a_draft_is_not_starved_by_a_running_pass(self, ready, monkeypatch):
        """T031 (FR-015, SC-006) — the test that matters most in this release.

        A real drafter request is issued while a pass is mid-flight, through
        the REAL engine/inference.py queue, and must resolve within its budget
        while single-flight stays intact.
        """
        import threading
        import time

        from engine import inference, matcher

        _seed_ranked(3)
        inference.reset_for_tests()
        # deterministic stand-ins for the models: an assessment is slow, a
        # draft is quick — the shape that matters, without loading a model
        inference.set_executors_for_tests({
            "chat": lambda p: ("SLOW" if p["messages"][-1]["content"] == "assess"
                               else "drafted") if not time.sleep(
                                   0.4 if p["messages"][-1]["content"] == "assess"
                                   else 0) else "",
            "embed": lambda p: [1.0],
        })

        def assess_through_the_real_queue(*_a):
            inference.run_chat([{"role": "user", "content": "assess"}])
            return matcher.MatchAnalysis(match_score=80, reasoning="a")

        monkeypatch.setattr(matcher, "analyze_match",
                            assess_through_the_real_queue)
        monkeypatch.delenv("JOBS_DISABLE_UPGRADE", raising=False)

        assert upgrade.start("test") is True

        draft_latency = {}

        def draft():
            started = time.monotonic()
            inference.run_chat([{"role": "user", "content": "draft"}])
            draft_latency["s"] = time.monotonic() - started

        time.sleep(0.1)  # let the pass get into the queue first
        thread = threading.Thread(target=draft)
        thread.start()
        thread.join(timeout=20)

        upgrade.join_for_tests(timeout=20)

        assert not thread.is_alive(), "the draft never resolved"
        assert "s" in draft_latency, "the draft raised instead of resolving"
        # waits behind at most ONE assessment, never the whole pass
        assert draft_latency["s"] < 1.5, draft_latency
        assert inference.max_observed_concurrency() == 1

        inference.set_executors_for_tests(None)
        inference.reset_for_tests()


class TestBackgroundWorkYieldsToTheApplicant:
    """021 US3 (FR-021). 020 made this pass stand down for a FILL SESSION,
    which left the other thing the applicant waits on — pressing "Tailor for
    this job" — queued behind a ~67 s assessment in a strict-FIFO queue,
    against its own deadline. That is one of the two reasons "generate a
    tailored resume" appeared to do nothing."""

    def test_no_claim_means_no_stand_down(self):
        assert upgrade.interactive_pending() is False
        assert upgrade._should_stand_down() is False

    def test_a_claim_stands_the_pass_down(self):
        with upgrade.interactive():
            assert upgrade.interactive_pending() is True
            assert upgrade._should_stand_down() is True
        assert upgrade.interactive_pending() is False

    def test_claims_nest(self):
        """Tailoring calls the drafter calls the matcher — an inner release
        must not un-pause the pass while the outer call is still running."""
        with upgrade.interactive():
            with upgrade.interactive():
                assert upgrade.interactive_pending() is True
            assert upgrade.interactive_pending() is True
        assert upgrade.interactive_pending() is False

    def test_a_claim_is_released_even_when_the_request_raises(self):
        """A leaked claim would make every later pass stand down forever,
        which reads as "the AI stopped working"."""
        with pytest.raises(ValueError):
            with upgrade.interactive():
                raise ValueError("boom")
        assert upgrade.interactive_pending() is False

    def test_the_pass_returns_to_work_once_the_applicant_is_served(
            self, monkeypatch):
        monkeypatch.setattr(upgrade, "PAUSE_POLL_S", 0.01)
        upgrade.begin_interactive()
        released = threading.Event()

        def release():
            time.sleep(0.05)
            upgrade.end_interactive()
            released.set()

        threading.Thread(target=release, daemon=True).start()
        assert upgrade._wait_out_any_session() is True
        assert released.is_set()

    def test_it_gives_up_rather_than_pausing_forever(self, monkeypatch):
        """Passes are resumable, so giving up is free — but hanging is not."""
        monkeypatch.setattr(upgrade, "PAUSE_POLL_S", 0.01)
        monkeypatch.setattr(upgrade, "MAX_PAUSE_S", 0.03)
        upgrade.begin_interactive()
        try:
            assert upgrade._wait_out_any_session() is False
        finally:
            upgrade.end_interactive()
