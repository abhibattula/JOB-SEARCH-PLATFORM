"""015 (US1, FR-001/FR-001a/FR-004): the single-owner on-device AI worker.

Every local-model call routes through engine/inference.py — ONE worker thread
executes strictly serially, callers get bounded waits (timeout → clean
RuntimeError), and a full queue fails immediately instead of piling callers
up. Tests use stub executors only; no real model is ever loaded here.
"""
from __future__ import annotations

import threading
import time

import pytest

from engine import inference


@pytest.fixture(autouse=True)
def _fresh_inference():
    inference.reset_for_tests()
    yield
    inference.reset_for_tests()


def test_chat_and_embed_route_through_executors():
    inference.set_executors_for_tests({
        "chat": lambda p: "reply:" + p["messages"][-1]["content"]
        + (":json" if p["json_mode"] else ""),
        "embed": lambda p: [float(len(p["text"])), 2.0],
    })
    out = inference.run_chat([{"role": "user", "content": "hi"}], json_mode=True)
    assert out == "reply:hi:json"
    assert inference.run_embed("abc") == [3.0, 2.0]


def test_hammer_executes_strictly_serially():
    """SC-001: 8 concurrent callers, zero overlap, every caller served."""
    active = {"now": 0, "max": 0}
    guard = threading.Lock()

    def slow_chat(payload):
        with guard:
            active["now"] += 1
            active["max"] = max(active["max"], active["now"])
        time.sleep(0.02)
        with guard:
            active["now"] -= 1
        return "ok"

    inference.set_executors_for_tests({"chat": slow_chat,
                                       "embed": lambda p: [1.0]})
    results: list[str] = []
    errors: list[Exception] = []

    def caller():
        for _ in range(3):
            try:
                results.append(inference.run_chat(
                    [{"role": "user", "content": "x"}], timeout_s=10))
            except Exception as exc:  # pragma: no cover - failure detail
                errors.append(exc)

    threads = [threading.Thread(target=caller) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)
    assert not errors
    assert results == ["ok"] * 24
    # the executor itself never overlapped…
    assert active["max"] == 1
    # …and the owner's own instrumentation agrees (FR-001)
    assert inference.max_observed_concurrency() == 1


def test_timeout_raises_clean_runtimeerror_and_worker_recovers():
    release = threading.Event()

    def stuck_chat(payload):
        release.wait(timeout=5)
        return "late"

    inference.set_executors_for_tests({"chat": stuck_chat,
                                       "embed": lambda p: [1.0]})
    with pytest.raises(RuntimeError) as err:
        inference.run_chat([{"role": "user", "content": "x"}], timeout_s=0.1)
    assert "timed out" in str(err.value)
    release.set()
    # the worker is not wedged: a fast call still completes
    inference.set_executors_for_tests({"chat": lambda p: "fast",
                                       "embed": lambda p: [1.0]})
    assert inference.run_chat([{"role": "user", "content": "x"}],
                              timeout_s=5) == "fast"


def test_abandoned_queued_request_is_never_executed():
    """A caller that timed out while QUEUED must not waste the worker's time
    later — its request is skipped, not executed."""
    release = threading.Event()
    executed: list[str] = []

    def chat(payload):
        executed.append(payload["messages"][-1]["content"])
        release.wait(timeout=5)
        return "done"

    inference.set_executors_for_tests({"chat": chat, "embed": lambda p: [1.0]})

    first_result: list[str] = []
    first = threading.Thread(target=lambda: first_result.append(
        inference.run_chat([{"role": "user", "content": "A"}], timeout_s=10)))
    first.start()
    for _ in range(100):  # wait until A is actually executing
        if executed:
            break
        time.sleep(0.01)
    assert executed == ["A"]

    # B queues behind the stuck A and gives up almost immediately
    with pytest.raises(RuntimeError):
        inference.run_chat([{"role": "user", "content": "B"}], timeout_s=0.05)

    release.set()
    first.join(timeout=5)
    assert first_result == ["done"]
    time.sleep(0.1)  # give the worker a beat to drain the abandoned request
    assert executed == ["A"]  # B was skipped, never executed


def test_full_queue_fails_immediately():
    """FR-001a: saturation is an instant clean failure, not unbounded waiting."""
    inference.reset_for_tests(queue_max=2)
    release = threading.Event()

    def blocked_chat(payload):
        release.wait(timeout=10)
        return "ok:" + payload["messages"][-1]["content"]

    inference.set_executors_for_tests({"chat": blocked_chat,
                                       "embed": lambda p: [1.0]})

    outcomes: dict[str, str] = {}

    def call(name):
        outcomes[name] = inference.run_chat(
            [{"role": "user", "content": name}], timeout_s=10)

    workers = [threading.Thread(target=call, args=(n,)) for n in "ABC"]
    for t in workers:
        t.start()
        time.sleep(0.05)  # A starts executing; B, C fill the queue (max 2)

    start = time.monotonic()
    with pytest.raises(RuntimeError) as err:
        inference.run_chat([{"role": "user", "content": "D"}], timeout_s=10)
    assert time.monotonic() - start < 0.5  # immediate, despite timeout_s=10
    assert "busy" in str(err.value).lower() or "full" in str(err.value).lower()

    release.set()
    for t in workers:
        t.join(timeout=5)
    assert outcomes == {"A": "ok:A", "B": "ok:B", "C": "ok:C"}


def test_executor_exception_becomes_runtimeerror():
    inference.set_executors_for_tests({
        "chat": lambda p: "ok",
        "embed": lambda p: (_ for _ in ()).throw(ValueError("boom")),
    })
    with pytest.raises(RuntimeError) as err:
        inference.run_embed("x", timeout_s=5)
    assert "boom" in str(err.value)


class TestWiring:
    """015 (T004): the two public model entrypoints route through the owner —
    no call site can reach a llama object off the worker thread."""

    def test_local_llm_chat_delegates_to_inference(self, monkeypatch):
        from engine import local_llm

        calls: list[tuple] = []

        def fake_run_chat(messages, json_mode=False, timeout_s=None):
            calls.append((messages, json_mode))
            return "stub-reply"

        monkeypatch.setattr(inference, "run_chat", fake_run_chat)
        # if chat() still used the old direct path, it would hit the (absent)
        # model and raise instead of returning the stub
        monkeypatch.setattr(local_llm, "_get_model", lambda: None)
        out = local_llm.chat([{"role": "user", "content": "q"}], json_mode=True)
        assert out == "stub-reply"
        assert calls == ([([{"role": "user", "content": "q"}], True)])

    def test_semantic_embed_delegates_and_maps_failure_to_none(self, monkeypatch):
        from engine import semantic

        monkeypatch.setattr(semantic, "available", lambda: True)
        monkeypatch.setattr(
            semantic, "_load",
            lambda: (_ for _ in ()).throw(
                AssertionError("model must not load on the caller thread")),
        )
        monkeypatch.setattr(inference, "run_embed",
                            lambda text, timeout_s=None: [1.0, 2.0])
        assert semantic.embed("hello") == [1.0, 2.0]

        def boom(text, timeout_s=None):
            raise RuntimeError("owner says no")

        monkeypatch.setattr(inference, "run_embed", boom)
        assert semantic.embed("hello") is None  # public contract: None, never raise

    def test_timeout_passes_through_the_whole_tier_chain(self, monkeypatch, tmp_db):
        """015 (FR-004 refinement): background long-form work (resume
        extraction: many chunks + a possible cold model load) must be able to
        declare its own budget — the interactive 180s default starved the
        offline extraction gate on a busy machine."""
        from engine import local_llm, matcher

        seen: dict = {}
        monkeypatch.setattr(
            inference, "run_chat",
            lambda m, json_mode=False, timeout_s=None:
            seen.update(t=timeout_s) or "ok")
        local_llm.chat([{"role": "user", "content": "q"}], timeout_s=42)
        assert seen["t"] == 42

        monkeypatch.setattr(matcher, "scoring_tier", lambda: "local")
        monkeypatch.setattr(
            matcher.local_llm, "chat",
            lambda messages, json_mode=False, timeout_s=None:
            seen.update(m=timeout_s) or "ok")
        matcher._chat([{"role": "user", "content": "x"}], purpose="json",
                      timeout_s=600)
        assert seen["m"] == 600

    def test_resume_extraction_declares_a_long_budget(self):
        import pathlib
        import re

        src = pathlib.Path("engine/resume_extract.py").read_text(encoding="utf-8")
        match = re.search(r"EXTRACTION_CHAT_TIMEOUT_S\s*=\s*(\d+)", src)
        assert match and int(match.group(1)) >= 600
        assert "timeout_s=EXTRACTION_CHAT_TIMEOUT_S" in src

    def test_raw_model_calls_stay_contained(self):
        """Static guard (FR-001): the raw llama calls exist ONLY inside the
        two executor homes; nothing else in engine/ may invoke them."""
        import pathlib

        chat_hits, embed_hits = [], []
        for path in pathlib.Path("engine").rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            if "create_chat_completion" in text:
                chat_hits.append(path.name)
            if "create_embedding" in text:
                embed_hits.append(path.name)
        assert chat_hits == ["local_llm.py"]
        assert embed_hits == ["semantic.py"]
        # and the owner binds to the executor functions, proving the route
        inf_src = pathlib.Path("engine/inference.py").read_text(encoding="utf-8")
        assert "_chat_impl" in inf_src and "_embed_impl" in inf_src


class TestSubprocessSpike:
    """015 (T007/R2, spike): JOBS_AI_SUBPROCESS=1 hosts the models in a
    supervised child — a native fault (the ggml crash class) kills the child,
    never the app. Stub-level: JOBS_AI_TEST_ECHO gives the child cheap
    deterministic executors so no model is ever loaded."""

    @pytest.fixture(autouse=True)
    def _subprocess_env(self, monkeypatch):
        monkeypatch.setenv("JOBS_AI_SUBPROCESS", "1")
        monkeypatch.setenv("JOBS_AI_TEST_ECHO", "1")
        inference.reset_for_tests()
        yield
        inference.reset_for_tests()

    def test_child_serves_chat_and_embed(self):
        out = inference.run_chat([{"role": "user", "content": "hi"}],
                                 timeout_s=30)
        assert out == "echo:hi"
        assert inference.run_embed("abcd", timeout_s=30) == [4.0]

    def test_child_death_fails_cleanly_and_recovers(self):
        import os
        import signal

        assert inference.run_chat([{"role": "user", "content": "warm"}],
                                  timeout_s=30) == "echo:warm"
        pid = inference._child_pid_for_tests()
        assert pid
        os.kill(pid, signal.SIGTERM)
        # the dead child fails at most a request or two, cleanly — and the
        # supervisor restarts it so a following request succeeds (SC-011)
        recovered = None
        for _ in range(3):
            try:
                recovered = inference.run_chat(
                    [{"role": "user", "content": "back"}], timeout_s=30)
                break
            except RuntimeError:
                continue
        assert recovered == "echo:back"
        assert inference.runtime_restart_count() >= 1

    def test_hung_child_is_terminated_on_timeout(self):
        with pytest.raises(RuntimeError):
            inference.run_chat([{"role": "user", "content": "SLEEP:10"}],
                               timeout_s=1)
        # the hang was contained: the child was restarted and serves again
        assert inference.run_chat([{"role": "user", "content": "ok"}],
                                  timeout_s=30) == "echo:ok"
        assert inference.runtime_restart_count() >= 1


def test_time_budgets_default_and_env_override(monkeypatch):
    monkeypatch.delenv("JOBS_AI_TIMEOUT_CHAT", raising=False)
    monkeypatch.delenv("JOBS_AI_TIMEOUT_EMBED", raising=False)
    assert inference._timeout_for("chat") == 180.0
    assert inference._timeout_for("embed") == 30.0
    monkeypatch.setenv("JOBS_AI_TIMEOUT_CHAT", "7")
    monkeypatch.setenv("JOBS_AI_TIMEOUT_EMBED", "3.5")
    assert inference._timeout_for("chat") == 7.0
    assert inference._timeout_for("embed") == 3.5
