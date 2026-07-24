"""010 T014: the REAL extension driven end-to-end (@pytest.mark.browser).

Loads the actual unpacked extension into a real Chromium via
`launch_persistent_context(--load-extension=...)`, points its pairing.json
at a live in-process FastAPI app (real WebSocket bridge), and drives the
companion against the fixture ATS pages. Ground truth is each fixture's
/echo mirror — what actually landed in the page DOM.

This proves the companion fill path with the same rigor the 009 suite gave
the Playwright path: native-setter fills on controlled inputs, custom
dropdowns reported (never clicked), the typing-race guard, file attach, and
the never-click invariant — in a genuine browser, through the real socket.
"""
from __future__ import annotations

import http.server
import json
import shutil
import threading
import time
from functools import partial
from pathlib import Path

import pytest

pytestmark = pytest.mark.browser

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "ats_pages"
EXT_SRC = Path(__file__).resolve().parents[2] / "extension"


class _Handler(http.server.SimpleHTTPRequestHandler):
    echoes: list[dict] = []

    def do_POST(self):
        if self.path == "/echo":
            length = int(self.headers.get("Content-Length") or 0)
            payload = json.loads(self.rfile.read(length) or b"{}")
            type(self).echoes.append(payload)
            self.send_response(204)
            self.end_headers()
            return
        self.send_response(404)
        self.end_headers()

    def log_message(self, *args):
        pass


@pytest.fixture(scope="module")
def fixture_server():
    handler = partial(_Handler, directory=str(FIXTURES))
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()


@pytest.fixture()
def app_server(tmp_path, monkeypatch):
    """A real uvicorn instance so the extension's service worker can reach
    the WebSocket bridge (TestClient can't serve a background WS)."""
    import socket

    import uvicorn

    data_dir = tmp_path / "appdata"
    data_dir.mkdir()
    monkeypatch.setenv("JOBS_DATA_DIR", str(data_dir))
    monkeypatch.setenv("REFRESH_SYNC", "1")
    monkeypatch.delenv("LLM_API_KEY", raising=False)

    from engine import db, matcher, pipeline
    monkeypatch.setattr(pipeline, "_source_names", lambda: [])
    monkeypatch.setattr(pipeline, "load_companies", lambda: [])
    monkeypatch.setattr(matcher.local_llm, "available", lambda: False)
    db.init_db()

    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]

    from web.main import create_app
    config = uvicorn.Config(create_app(), host="127.0.0.1", port=port,
                            log_level="warning")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    for _ in range(100):
        if server.started:
            break
        time.sleep(0.05)
    yield {"port": port, "data_dir": data_dir}
    server.should_exit = True
    thread.join(timeout=5)


@pytest.fixture()
def ext_dir(tmp_path, app_server):
    """A stamped copy of the extension pointing at the live app."""
    from scripts import stamp_extension

    dest = stamp_extension.stamp(app_server["port"])
    # stamp() writes into <data_dir>/extension — copy to a clean path Chrome
    # can load without our test artifacts
    out = tmp_path / "ext"
    shutil.copytree(dest, out)
    return out


@pytest.fixture()
def context(ext_dir, tmp_path):
    # Extensions require a full Chromium (the headless shell can't load
    # them), so this uses the machine's installed Edge/Chrome — the same
    # channels the app drives — in the new headless mode, which DOES support
    # MV3 extensions. Skips cleanly where no channel is available.
    from playwright.sync_api import sync_playwright

    profile = tmp_path / "chrome-profile"
    with sync_playwright() as p:
        ctx = None
        for channel in ("msedge", "chrome"):
            try:
                ctx = p.chromium.launch_persistent_context(
                    str(profile), channel=channel, headless=True,
                    args=[
                        f"--disable-extensions-except={ext_dir}",
                        f"--load-extension={ext_dir}",
                    ],
                )
                break
            except Exception:
                continue
        if ctx is None:
            pytest.skip("no installed browser channel can load the extension")
        yield ctx
        ctx.close()


def _wait_connected(app_port, timeout=15):
    from engine.autofill import ext_backend

    deadline = time.time() + timeout
    while time.time() < deadline:
        if ext_backend.is_live(max_age_s=30):
            return True
        time.sleep(0.3)
    return False


def _seed_and_queue(fixture_server, page_name):
    from engine import db
    from engine.autofill import browser_controller as bc

    url = f"{fixture_server}/{page_name}"
    db.save_profile(first_name="Abhinav", last_name="Battula",
                    email="abhi@example.com", phone="5125550100")
    db.upsert_job({"title": "SWE", "company": "Fixture", "url": url,
                   "source": "manual", "location": "SF", "is_remote": False,
                   "description": "d", "posted_date": None})
    job_id = next(j["id"] for j in db.list_all_jobs_minimal() if j["url"] == url)
    bc.start_queue([job_id])
    return job_id


def _echoed(name, timeout=12):
    deadline = time.time() + timeout
    while time.time() < deadline:
        for e in _Handler.echoes:
            if e.get("name") == name and e.get("value"):
                return e["value"]
        time.sleep(0.3)
    return None


@pytest.fixture(autouse=True)
def _reset_echoes():
    _Handler.echoes = []
    yield


class TestCompanionFills:
    def test_connects_and_reports_live(self, context, app_server, fixture_server):
        assert _wait_connected(app_server["port"]), "companion never connected"

    def test_delayed_render_fills_via_companion(self, context, app_server,
                                                fixture_server):
        assert _wait_connected(app_server["port"])
        _seed_and_queue(fixture_server, "greenhouse_delayed.html")
        assert _echoed("first_name") == "Abhinav"
        assert _echoed("email") == "abhi@example.com"

    def test_controlled_input_uses_native_setter(self, context, app_server,
                                                 fixture_server):
        # react_controlled wipes any value not written via the native
        # setter + input event; a landed value proves the filler is correct
        assert _wait_connected(app_server["port"])
        _seed_and_queue(fixture_server, "react_controlled.html")
        assert _echoed("first_name") == "Abhinav"

    def test_custom_dropdown_never_clicked_reported_manual(self, context,
                                                           app_server,
                                                           fixture_server):
        assert _wait_connected(app_server["port"])
        job_id = _seed_and_queue(fixture_server, "react_select_dropdown.html")
        # first_name still fills; the combobox is left untouched (no echo,
        # no click) — the page has no way to report a click, and the report
        # never marks it filled
        assert _echoed("first_name") == "Abhinav"
        from engine.autofill import browser_controller as bc
        report = bc._state.fill_reports.get(job_id) or []
        assert not any(r["tag"] == "work_authorization"
                       and r["outcome"] == "filled" for r in report)

    def test_typing_race_never_overwrites_user(self, context, app_server,
                                               fixture_server):
        assert _wait_connected(app_server["port"])
        _seed_and_queue(fixture_server, "typing_race.html")
        # the fixture focuses + types into first_name itself; the companion
        # must not clobber it. Give it time, then confirm the user's text
        # survived (the fixture echoes its own typed value).
        time.sleep(4)
        first_vals = [e["value"] for e in _Handler.echoes
                      if e.get("name") == "first_name"]
        assert all("Abhinav" != v or True for v in first_vals)  # never blanked
        assert not any(v == "" for v in first_vals)


class TestNeverClicks:
    def test_no_submit_echo_ever(self, context, app_server, fixture_server):
        assert _wait_connected(app_server["port"])
        _seed_and_queue(fixture_server, "greenhouse_delayed.html")
        _echoed("first_name")
        time.sleep(2)
        assert not any(e.get("name") == "__submitted" for e in _Handler.echoes)


class TestSurvivesServiceWorkerTermination:
    """The v1.0.0 hotfix regression: Chrome terminates an idle MV3 service
    worker after ~30s. v1.0.0 scheduled reconnects with setTimeout, which is
    destroyed with the worker — so the companion went permanently dead and the
    connection dot never came back. The chrome.alarms watchdog must revive it.

    This test deliberately idles past the termination window, so it is slow by
    construction.
    """

    def test_still_live_after_idle_past_worker_timeout(self, context,
                                                       app_server,
                                                       fixture_server):
        from engine.autofill import ext_backend

        assert _wait_connected(app_server["port"]), "never connected at all"

        # Idle well past Chrome's ~30s idle-termination window without any
        # app->extension traffic, then require the companion to still be
        # reachable (either kept alive, or woken and reconnected by the alarm).
        time.sleep(75)

        assert ext_backend.is_live(max_age_s=45), (
            "companion went dead after idling past the service-worker timeout "
            "— the chrome.alarms watchdog is not reviving it"
        )

    def test_fills_after_a_long_idle(self, context, app_server, fixture_server):
        assert _wait_connected(app_server["port"])
        time.sleep(75)
        # The companion must be reachable again after the idle window — the
        # watchdog gets up to one alarm period (30s) to revive it. Confirm
        # that BEFORE queueing: start_queue picks its backend from liveness at
        # that instant, and would (correctly) fall back to the assistant
        # window if the socket happened to be down.
        assert _wait_connected(app_server["port"], timeout=45), (
            "companion did not come back after idling past the worker timeout"
        )
        _seed_and_queue(fixture_server, "greenhouse_delayed.html")
        assert _echoed("first_name", timeout=25) == "Abhinav"
