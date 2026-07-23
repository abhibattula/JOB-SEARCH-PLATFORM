"""The dedicated Playwright-owner thread for Apply Assist (feature 009,
FR-001).

Root causes A5/A6: v0.5-v0.8 touched Playwright objects from FastAPI
request threads and from sync-API event callbacks — both forbidden — so
jobs #2+, re-scans, and the multi-page refill silently broke. This module
makes those bugs structurally impossible: exactly ONE daemon thread ever
touches Playwright, commands arrive through a queue, and the queue-wait
timeout IS the watch-tick scheduler (commands preempt instantly; an idle
timeout runs one watch tick when a job is current).

Routes/facade callers NEVER block on browser work — dispatch() returns
immediately unless a short ack wait is requested (RESOLVE_PENDING only).
"""
from __future__ import annotations

import logging
import os
import queue
import threading
from dataclasses import dataclass, field

log = logging.getLogger(__name__)

TICK_SECONDS = 2.0  # steady cadence, no idle backoff (spec clarification)


@dataclass
class Command:
    name: str
    payload: dict = field(default_factory=dict)
    done: threading.Event | None = None


_commands: "queue.Queue[Command]" = queue.Queue()
_thread: threading.Thread | None = None
_thread_lock = threading.Lock()


def _tick_seconds() -> float:
    return float(os.environ.get("AUTOFILL_TICK_SECONDS", TICK_SECONDS))


def ensure_thread() -> None:
    global _thread
    with _thread_lock:
        if _thread is None or not _thread.is_alive():
            _thread = threading.Thread(
                target=_run, name="apply-assist-worker", daemon=True
            )
            _thread.start()


def dispatch(name: str, payload: dict | None = None, wait: float | None = None) -> bool:
    """Enqueue a command for the worker. Returns immediately; with `wait`,
    blocks up to that many seconds for the handler to finish (used only by
    RESOLVE_PENDING's short ack). True = acked (or fire-and-forget)."""
    ensure_thread()
    done = threading.Event() if wait else None
    _commands.put(Command(name, payload or {}, done))
    if done is not None:
        return done.wait(wait)
    return True


def _assert_worker_thread() -> None:
    """Guard at the top of every Playwright-touching function: the class of
    bug where a request thread touches a Page can never come back silently."""
    if threading.current_thread() is not _thread:
        raise RuntimeError(
            "Playwright objects may only be touched on the apply-assist"
            " worker thread"
        )


def drain_for_tests() -> None:
    """Test hook: wait until every queued command has been consumed so a
    test's monkeypatched handlers can't be called after its teardown."""
    _commands.join()


def _handle(cmd: Command) -> None:
    from . import browser_controller as bc

    handlers = {
        "OPEN_JOB": lambda: bc._worker_open_job(cmd.payload["job_id"]),
        "OPEN_PRACTICE": lambda: bc._worker_open_practice(cmd.payload["url"]),
        "FORCE_TICK": lambda: bc._tick_if_active(force=True),
        "CLOSE_PAGE": lambda: bc._worker_close_page(),
        "RESOLVE_PENDING": lambda: bc._worker_resolve_pending(cmd.payload),
        "SHUTDOWN_CONTEXT": lambda: bc._worker_shutdown_context(),
    }
    handler = handlers.get(cmd.name)
    if handler is None:
        log.warning("unknown worker command %r", cmd.name)
        return
    handler()


def _run() -> None:
    from . import browser_controller as bc

    while True:
        try:
            cmd = _commands.get(timeout=_tick_seconds())
        except queue.Empty:
            try:
                bc._tick_if_active()
            except Exception:
                log.warning("watch tick failed", exc_info=True)
            continue
        try:
            _handle(cmd)
        except Exception:
            log.warning("worker command %s failed", cmd.name, exc_info=True)
        finally:
            if cmd.done is not None:
                cmd.done.set()
            _commands.task_done()
