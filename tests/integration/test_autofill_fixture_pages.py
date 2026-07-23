"""009 T016: the real-browser regression suite (@pytest.mark.browser).

Runs the ACTUAL live fill engine — real worker thread, real headless
installed Edge/Chrome — against local fixture pages that reproduce every
confirmed root-cause class: delayed JS render (A1), iframe embedding (A4),
bracket-name attributes (A8), Ashby-style system fields, a form revealed
by an Apply click the page itself simulates, and a typing race.

Ground truth is the fixture pages' own /echo mirror: every real DOM value
change is POSTed back to the test server, so assertions are about what
actually landed in the page — not what the engine believes it wrote.

This layer's absence is what let a non-working fill engine ship twice.
Excluded from the default run (pytest.ini); CI runs `pytest -m browser`.
"""
from __future__ import annotations

import http.server
import json
import threading
import time
from functools import partial
from pathlib import Path

import pytest

from engine import db
from engine.autofill import browser_controller as bc
from engine.autofill import worker

pytestmark = pytest.mark.browser

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "ats_pages"


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

    def log_message(self, *args):  # keep test output clean
        pass


@pytest.fixture(scope="module")
def server():
    handler = partial(_Handler, directory=str(FIXTURES))
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{httpd.server_address[1]}"
    yield base
    httpd.shutdown()


@pytest.fixture(scope="module", autouse=True)
def _browser_available():
    probe = bc.preflight()
    if not probe["ok"]:
        pytest.skip(f"no installed browser channel available: {probe['error']}")
    yield
    # tear the real browser down at module end
    worker.dispatch("SHUTDOWN_CONTEXT", wait=10.0)


@pytest.fixture(autouse=True)
def _fast_headless(monkeypatch):
    monkeypatch.setenv("AUTOFILL_HEADLESS", "1")
    monkeypatch.setenv("AUTOFILL_TICK_SECONDS", "0.7")
    _Handler.echoes = []
    yield
    bc.stop_queue()
    worker.drain_for_tests()


@pytest.fixture()
def profile(tmp_db, tmp_path):
    resume = tmp_path / "resume.pdf"
    resume.write_bytes(b"%PDF-1.4 practice resume")
    db.save_profile(
        first_name="Abhinav", last_name="Battula", email="abhi@example.com",
        phone="(512) 555-0100", linkedin_url="https://linkedin.com/in/abhinav",
        portfolio_url="https://github.com/abhinav",
        resume_file_path=str(resume),
    )
    db.set_setting("AUTOFILL_USE_TAILORED_PDF", "0")  # attach the file above
    return resume


def seed_fixture_job(url):
    db.upsert_job({
        "title": f"Fixture {url.rsplit('/', 1)[-1]}", "company": "FixtureCo",
        "url": url, "source": "greenhouse", "description": "d",
    })
    jobs, _ = db.query_jobs(window=None, statuses=None, entry_level=None)
    return next(j for j in jobs if j["url"] == url)["id"]


def echoed() -> dict:
    """name -> last echoed real-DOM value."""
    values = {}
    for entry in _Handler.echoes:
        values[entry["name"]] = entry["value"]
    return values


def wait_for(predicate, timeout=30.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.3)
    return False


def run_job(url):
    job_id = seed_fixture_job(url)
    result = bc.start_queue([job_id])
    assert result is not None
    return job_id


class TestDelayedRender:
    def test_fields_fill_after_late_mount(self, profile, server):
        run_job(f"{server}/greenhouse_delayed.html")
        assert wait_for(lambda: {"first_name", "last_name", "email", "phone"}
                        <= set(echoed())), f"echoes: {echoed()}"
        values = echoed()
        assert values["first_name"] == "Abhinav"
        assert values["last_name"] == "Battula"
        assert values["email"] == "abhi@example.com"
        assert "512" in values["phone"]
        # the resume file input received the real file
        assert wait_for(lambda: "resume" in echoed())
        assert echoed()["resume"].endswith("resume.pdf")

    def test_activity_reports_watching_with_counts(self, profile, server):
        run_job(f"{server}/greenhouse_delayed.html")
        assert wait_for(
            lambda: bc.queue_snapshot()["activity"]["fields_filled"] >= 4
        )
        activity = bc.queue_snapshot()["activity"]
        assert activity["phase"] == "watching"
        assert activity["fields_seen"] >= 5


class TestIframeEmbedding:
    def test_fields_inside_iframe_fill(self, profile, server):
        run_job(f"{server}/greenhouse_iframe_host.html")
        assert wait_for(lambda: "job_application[first_name]" in echoed()
                        and "job_application[email]" in echoed()), f"echoes: {echoed()}"
        values = echoed()
        assert values["job_application[first_name]"] == "Abhinav"
        assert values["job_application[email]"] == "abhi@example.com"


class TestBracketNames:
    def test_lever_style_names_fill(self, profile, server):
        run_job(f"{server}/lever_apply.html")
        assert wait_for(lambda: {"name", "email", "urls[LinkedIn]"} <= set(echoed()))
        values = echoed()
        assert values["name"] == "Abhinav Battula"
        assert values["urls[LinkedIn]"] == "https://linkedin.com/in/abhinav"
        assert wait_for(lambda: "resume" in echoed())


class TestAshbyStyle:
    def test_systemfields_fill_after_react_mount(self, profile, server):
        run_job(f"{server}/ashby_application.html")
        assert wait_for(lambda: {"_systemfield_name", "_systemfield_email"}
                        <= set(echoed()))
        values = echoed()
        assert values["_systemfield_name"] == "Abhinav Battula"
        assert values["_systemfield_email"] == "abhi@example.com"


class TestFormBehindApplyButton:
    def test_user_revealed_form_fills(self, profile, server):
        run_job(f"{server}/posting_with_apply_button.html")
        activity = None
        # before the (page-simulated) user clicks Apply: guidance phase
        assert wait_for(
            lambda: bc.queue_snapshot()["activity"]["phase"] == "waiting_for_form",
            timeout=10,
        )
        # after the click reveals the form, the fields fill
        assert wait_for(lambda: {"first_name", "email"} <= set(echoed()))
        assert echoed()["first_name"] == "Abhinav"


class TestTypingRace:
    def test_focused_field_is_never_overwritten(self, profile, server):
        run_job(f"{server}/typing_race.html")
        assert wait_for(lambda: "email" in echoed())
        # give the race script time to finish typing + blur
        wait_for(lambda: echoed().get("first_name") == "UserTyped", timeout=15)
        assert echoed()["email"] == "abhi@example.com"
        # the user's typed value survived every tick
        assert echoed()["first_name"] == "UserTyped"
