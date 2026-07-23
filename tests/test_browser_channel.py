"""008 US1 (T006/T008): channel-based browser launch + reason-class outcomes.

Apply Assist drives the user's INSTALLED Edge/Chrome via Playwright channels
(FR-007) — nothing is downloaded — and every failure carries a distinct
reason class with detail text (FR-009).
"""
import pytest

from engine import db
from engine.autofill import browser_controller as bc


# --- playwright fakes --------------------------------------------------------

class FakeContext:
    def __init__(self):
        self.pages = []
        self.closed = False

    def new_page(self):
        page = FakePage()
        self.pages.append(page)
        return page

    def close(self):
        self.closed = True


class FakePage:
    def __init__(self, goto_error=None, serialize_error=None, fields=None):
        self.goto_error = goto_error
        self.serialize_error = serialize_error
        self.fields = fields if fields is not None else []
        self.gotos = []

    def on(self, event, handler):
        pass

    def goto(self, url, timeout=None):
        if self.goto_error:
            raise self.goto_error
        self.gotos.append(url)

    def eval_on_selector_all(self, selector, script):
        if self.serialize_error:
            raise self.serialize_error
        return self.fields

    def query_selector(self, selector):
        return None


class FakeChromium:
    def __init__(self, fail_channels=(), persistent_fail_channels=None):
        self.fail_channels = set(fail_channels)
        self.persistent_fail = (
            set(persistent_fail_channels)
            if persistent_fail_channels is not None
            else set(fail_channels)
        )
        self.persistent_calls = []
        self.launch_calls = []

    def launch_persistent_context(self, user_data_dir, channel=None, headless=None):
        self.persistent_calls.append(
            {"user_data_dir": user_data_dir, "channel": channel, "headless": headless}
        )
        if channel in self.persistent_fail:
            raise RuntimeError(f"browser channel {channel} is not installed")
        return FakeContext()

    def launch(self, channel=None, headless=None):
        self.launch_calls.append({"channel": channel, "headless": headless})
        if channel in self.fail_channels:
            raise RuntimeError(f"browser channel {channel} is not installed")

        class _B:
            def close(self):
                pass

        return _B()


class FakePlaywright:
    def __init__(self, chromium):
        self.chromium = chromium
        self.stopped = False

    def stop(self):
        self.stopped = True


class FakeSyncPlaywright:
    """Stands in for playwright.sync_api.sync_playwright() — supports both
    .start() (persistent session) and context-manager use (preflight)."""

    def __init__(self, pw):
        self.pw = pw

    def start(self):
        return self.pw

    def __enter__(self):
        return self.pw

    def __exit__(self, *exc):
        self.pw.stop()
        return False


@pytest.fixture()
def fake_playwright(monkeypatch):
    def make(**chromium_kwargs):
        chromium = FakeChromium(**chromium_kwargs)
        pw = FakePlaywright(chromium)
        import playwright.sync_api

        monkeypatch.setattr(
            playwright.sync_api, "sync_playwright", lambda: FakeSyncPlaywright(pw)
        )
        return chromium, pw

    yield make
    # never leak a fake context into other tests
    bc._context = None
    bc._playwright = None


def seed_job(url="https://x.example/apply/1"):
    db.upsert_job(
        {"title": f"SWE {url.rsplit('/', 1)[-1]}", "company": "TestCo", "url": url,
         "source": "greenhouse", "description": "d"}
    )
    jobs, _ = db.query_jobs(window=None, statuses=None, entry_level=None)
    return next(j for j in jobs if j["url"] == url)["id"]


class TestChannelLaunch:
    def test_launches_installed_edge_first(self, tmp_db, fake_playwright):
        chromium, _ = fake_playwright()
        context = bc._ensure_context()
        assert isinstance(context, FakeContext)
        call = chromium.persistent_calls[0]
        assert call["channel"] == "msedge"
        assert call["headless"] is False
        assert "browser-profile" in str(call["user_data_dir"])

    def test_falls_back_to_chrome(self, tmp_db, fake_playwright):
        chromium, _ = fake_playwright(fail_channels=("msedge",))
        bc._ensure_context()
        assert [c["channel"] for c in chromium.persistent_calls] == [
            "msedge", "chrome"
        ]

    def test_raises_browser_unavailable_with_detail(self, tmp_db, fake_playwright):
        chromium, pw = fake_playwright(fail_channels=("msedge", "chrome"))
        with pytest.raises(bc.BrowserUnavailable) as excinfo:
            bc._ensure_context()
        message = str(excinfo.value)
        assert "msedge" in message and "chrome" in message
        assert pw.stopped  # no half-started playwright left behind


class TestPreflight:
    def test_preflight_ok_reports_channel(self, tmp_db, fake_playwright):
        fake_playwright()
        result = bc.preflight()
        assert result == {"ok": True, "channel": "msedge", "error": None}

    def test_preflight_failure_reports_error_text(self, tmp_db, fake_playwright):
        fake_playwright(fail_channels=("msedge", "chrome"))
        result = bc.preflight()
        assert result["ok"] is False
        assert result["channel"] is None
        assert "not installed" in result["error"]


class TestReasonClassOutcomes:
    """009: launch/nav failures carry distinct reasons; scan trouble needs
    3 consecutive failed ticks; zero visible fields is NOT a failure — the
    watcher keeps watching and the activity feed guides the user."""

    def _inline_dispatch(self, monkeypatch):
        from engine.autofill import worker

        # sanctioned inline mode: these tests run the worker-side handlers
        # on the test thread, so the (working) confinement guard is waived
        monkeypatch.setattr(worker, "_assert_worker_thread", lambda: None)
        monkeypatch.setattr(
            bc, "_dispatch",
            lambda name, payload=None, wait=None:
                bc._worker_open_job(payload["job_id"]) if name == "OPEN_JOB" else None,
        )

    def test_launch_failure_marks_launch_failed(self, tmp_db, monkeypatch):
        job_id = seed_job()

        def boom():
            raise bc.BrowserUnavailable("msedge: nope; chrome: nope")

        monkeypatch.setattr(bc, "_ensure_context", boom)
        self._inline_dispatch(monkeypatch)
        bc.start_queue([job_id])
        outcome = next(
            o for o in bc.queue_snapshot()["outcomes"] if o["job_id"] == job_id
        )
        assert outcome["reason"] == "launch_failed"
        assert "nope" in outcome["detail"]
        assert bc.current_job()["fell_back"] is True
        assert bc.queue_snapshot()["activity"]["phase"] == "error"

    def test_nav_failure_marks_nav_failed(self, tmp_db, monkeypatch):
        job_id = seed_job()
        page = ChannelFakePage(goto_error=RuntimeError("net::ERR_NAME_NOT_RESOLVED"))
        context = ChannelFakeContext(page)
        monkeypatch.setattr(bc, "_ensure_context", lambda: context)
        self._inline_dispatch(monkeypatch)
        bc.start_queue([job_id])
        outcome = next(
            o for o in bc.queue_snapshot()["outcomes"] if o["job_id"] == job_id
        )
        assert outcome["reason"] == "nav_failed"
        assert "ERR_NAME_NOT_RESOLVED" in outcome["detail"]

    def test_scan_failed_needs_three_consecutive_bad_ticks(self, tmp_db, monkeypatch):
        from tests.test_watcher import FakeFrame

        job_id = seed_job()
        bad_frame = FakeFrame(fail_serialize=True)
        page = ChannelFakePage(frames=[bad_frame])
        context = ChannelFakeContext(page)
        monkeypatch.setattr(bc, "_ensure_context", lambda: context)
        self._inline_dispatch(monkeypatch)
        bc.start_queue([job_id])  # open runs one forced tick -> 1 failure
        outcomes = bc.queue_snapshot()["outcomes"]
        assert not any(o["reason"] == "scan_failed" for o in outcomes)
        bc._tick_if_active()
        bc._tick_if_active()  # third consecutive failure
        outcome = next(
            o for o in bc.queue_snapshot()["outcomes"] if o["job_id"] == job_id
        )
        assert outcome["reason"] == "scan_failed"
        # a later healthy tick clears it (no terminal states while current)
        bad_frame.fail_serialize = False
        bc._tick_if_active()
        assert not any(
            o["reason"] == "scan_failed"
            for o in bc.queue_snapshot()["outcomes"]
        )

    def test_zero_fields_is_waiting_not_failure(self, tmp_db, monkeypatch):
        from tests.test_watcher import FakeFrame

        job_id = seed_job()
        page = ChannelFakePage(frames=[FakeFrame(descriptors=[])])
        context = ChannelFakeContext(page)
        monkeypatch.setattr(bc, "_ensure_context", lambda: context)
        self._inline_dispatch(monkeypatch)
        bc.start_queue([job_id])
        assert bc.queue_snapshot()["outcomes"] == []
        activity = bc.queue_snapshot()["activity"]
        assert activity["phase"] == "waiting_for_form"
        assert "Apply" in activity["message"]

    def test_fields_fill_and_activity_counts(self, tmp_db, monkeypatch):
        from engine import db as edb
        from tests.test_watcher import FakeFrame, descriptor

        edb.save_profile(first_name="Ada", email="ada@example.com")
        job_id = seed_job()
        frame = FakeFrame(descriptors=[
            descriptor(name="first_name"),
            descriptor(name="email", type="email"),
        ])
        page = ChannelFakePage(frames=[frame])
        context = ChannelFakeContext(page)
        monkeypatch.setattr(bc, "_ensure_context", lambda: context)
        self._inline_dispatch(monkeypatch)
        bc.start_queue([job_id])
        activity = bc.queue_snapshot()["activity"]
        assert activity["phase"] == "watching"
        assert activity["fields_seen"] == 2
        assert activity["fields_filled"] == 2
        report = bc.queue_snapshot()["fill_report"]
        assert {r["outcome"] for r in report} == {"filled"}

    def test_batch_summary_counts_fallback_reasons_as_manual(
        self, tmp_db, monkeypatch
    ):
        j1, j2 = seed_job("https://x.example/1"), seed_job("https://x.example/2")
        monkeypatch.setattr(bc, "_dispatch", lambda name, payload=None, wait=None: None)
        bc.start_queue([j1, j2])
        with bc._lock:
            bc._state.outcomes[j1] = {"reason": "launch_failed", "detail": "x"}
        bc.advance()
        bc.advance()
        summary = bc.queue_snapshot()["summary"]
        assert summary["manual"] == 1
        assert summary["skipped"] == 1


class ChannelFakePage:
    def __init__(self, goto_error=None, frames=None):
        self.goto_error = goto_error
        self._frames = frames if frames is not None else []
        self.closed = False

    def goto(self, url, timeout=None):
        if self.goto_error:
            raise self.goto_error

    @property
    def frames(self):
        return self._frames

    def close(self):
        self.closed = True


class ChannelFakeContext:
    def __init__(self, page):
        self._page = page

    def new_page(self):
        return self._page

    def close(self):
        pass
