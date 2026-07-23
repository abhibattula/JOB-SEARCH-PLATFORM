"""009 T006: the dedicated Playwright-owner thread (FR-001).

Playwright is never touched here — command handlers in browser_controller
are monkeypatched. What IS tested: ordering, tick scheduling, thread
confinement, ack semantics, and thread survival.
"""
import threading
import time

import pytest

from engine.autofill import browser_controller as bc
from engine.autofill import worker


@pytest.fixture(autouse=True)
def fast_ticks(monkeypatch):
    monkeypatch.setenv("AUTOFILL_TICK_SECONDS", "0.05")
    yield
    worker.drain_for_tests()


def wait_until(predicate, timeout=2.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return False


class TestCommandProcessing:
    def test_commands_processed_in_order_on_worker_thread(self, monkeypatch):
        seen = []

        def open_job(job_id):
            worker._assert_worker_thread()  # must run ON the worker
            seen.append(("open", job_id))

        monkeypatch.setattr(bc, "_worker_open_job", open_job)
        monkeypatch.setattr(bc, "_worker_close_page", lambda: seen.append(("close",)))
        worker.dispatch("OPEN_JOB", {"job_id": 1})
        worker.dispatch("CLOSE_PAGE")
        worker.dispatch("OPEN_JOB", {"job_id": 2})
        assert wait_until(lambda: len(seen) == 3)
        assert seen == [("open", 1), ("close",), ("open", 2)]

    def test_dispatch_with_wait_acks_within_deadline(self, monkeypatch):
        monkeypatch.setattr(bc, "_worker_resolve_pending", lambda payload: None)
        acked = worker.dispatch("RESOLVE_PENDING", {"answer": "x"}, wait=0.5)
        assert acked is True

    def test_handler_exception_does_not_kill_the_thread(self, monkeypatch):
        calls = []

        def boom(job_id):
            calls.append("boom")
            raise RuntimeError("handler exploded")

        monkeypatch.setattr(bc, "_worker_open_job", boom)
        monkeypatch.setattr(bc, "_worker_close_page", lambda: calls.append("close"))
        worker.dispatch("OPEN_JOB", {"job_id": 1})
        worker.dispatch("CLOSE_PAGE")
        assert wait_until(lambda: calls == ["boom", "close"])

    def test_unknown_command_is_ignored(self, monkeypatch):
        monkeypatch.setattr(bc, "_worker_close_page", lambda: None)
        assert worker.dispatch("NO_SUCH_COMMAND", wait=0.5) is True  # acked, ignored


class TestTickScheduling:
    def test_ticks_fire_between_commands(self, monkeypatch):
        ticks = []
        monkeypatch.setattr(bc, "_tick_if_active", lambda force=False: ticks.append(1))
        worker.ensure_thread()
        assert wait_until(lambda: len(ticks) >= 2, timeout=2.0)

    def test_command_preempts_waiting_tick(self, monkeypatch):
        order = []
        monkeypatch.setattr(bc, "_tick_if_active", lambda force=False: order.append("tick"))
        monkeypatch.setattr(
            bc, "_worker_close_page", lambda: order.append("cmd")
        )
        worker.dispatch("CLOSE_PAGE", wait=1.0)
        assert "cmd" in order


class TestThreadConfinement:
    def test_assert_worker_thread_raises_off_thread(self):
        worker.ensure_thread()
        with pytest.raises(RuntimeError, match="worker thread"):
            worker._assert_worker_thread()

    def test_assert_passes_on_worker_thread(self, monkeypatch):
        result = {}

        def probe():
            try:
                worker._assert_worker_thread()
                result["ok"] = True
            except RuntimeError:
                result["ok"] = False

        monkeypatch.setattr(bc, "_worker_close_page", probe)
        worker.dispatch("CLOSE_PAGE", wait=1.0)
        assert result.get("ok") is True

    def test_single_thread_reused_across_dispatches(self):
        worker.ensure_thread()
        first = worker._thread
        worker.ensure_thread()
        assert worker._thread is first
        assert first.daemon
