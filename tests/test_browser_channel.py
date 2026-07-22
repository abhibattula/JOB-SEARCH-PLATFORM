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
        {"title": "SWE", "company": "TestCo", "url": url,
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
    def test_launch_failure_marks_launch_failed(self, tmp_db, monkeypatch):
        job_id = seed_job()

        def boom():
            raise bc.BrowserUnavailable("msedge: nope; chrome: nope")

        monkeypatch.setattr(bc, "_ensure_context", boom)
        bc.start_queue([job_id])
        snapshot = bc.queue_snapshot()
        outcome = next(o for o in snapshot["outcomes"] if o["job_id"] == job_id)
        assert outcome["reason"] == "launch_failed"
        assert "nope" in outcome["detail"]
        assert bc.current_job()["fell_back"] is True

    def test_nav_failure_marks_nav_failed(self, tmp_db, monkeypatch):
        job_id = seed_job()
        context = FakeContext()
        page = FakePage(goto_error=RuntimeError("net::ERR_NAME_NOT_RESOLVED"))
        context.new_page = lambda: page
        monkeypatch.setattr(bc, "_ensure_context", lambda: context)
        bc.start_queue([job_id])
        outcome = next(
            o for o in bc.queue_snapshot()["outcomes"] if o["job_id"] == job_id
        )
        assert outcome["reason"] == "nav_failed"
        assert "ERR_NAME_NOT_RESOLVED" in outcome["detail"]

    def test_scan_failure_marks_scan_failed(self, tmp_db, monkeypatch):
        job_id = seed_job()
        context = FakeContext()
        page = FakePage(serialize_error=RuntimeError("Execution context destroyed"))
        context.new_page = lambda: page
        monkeypatch.setattr(bc, "_ensure_context", lambda: context)
        bc.start_queue([job_id])
        outcome = next(
            o for o in bc.queue_snapshot()["outcomes"] if o["job_id"] == job_id
        )
        assert outcome["reason"] == "scan_failed"

    def test_unrecognized_page_marks_unrecognized(self, tmp_db, monkeypatch):
        job_id = seed_job()
        context = FakeContext()
        page = FakePage(fields=[])  # nothing classifiable on the page
        context.new_page = lambda: page
        monkeypatch.setattr(bc, "_ensure_context", lambda: context)
        bc.start_queue([job_id])
        outcome = next(
            o for o in bc.queue_snapshot()["outcomes"] if o["job_id"] == job_id
        )
        assert outcome["reason"] == "unrecognized"

    def test_batch_summary_counts_all_reason_classes_as_manual(
        self, tmp_db, monkeypatch
    ):
        j1, j2 = seed_job("https://x.example/1"), seed_job("https://x.example/2")
        monkeypatch.setattr(bc, "_open_job", lambda job_id: None)
        bc.start_queue([j1, j2])
        with bc._lock:
            bc._state.outcomes[j1] = {"reason": "launch_failed", "detail": "x"}
        bc.advance()
        bc.advance()
        summary = bc.queue_snapshot()["summary"]
        assert summary["manual"] == 1
        assert summary["skipped"] == 1
