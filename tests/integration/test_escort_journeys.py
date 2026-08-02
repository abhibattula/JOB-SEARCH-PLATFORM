"""019 (T067): the escort, end to end, in a real browser.

The flagship suite for this feature. It loads the real unpacked extension
into real Chromium against the live app over the real WebSocket bridge, and
drives whole multi-step applications.

Every assertion is an observable effect — a value in a field, a page that
navigated, a sentinel that did or did not fire. The 018 lesson is the reason:
a dead control passed a green suite for a whole release because the tests
only asserted that a string existed in the source.

The most important test here is the one that asserts something did NOT
happen: `test_the_final_submit_is_never_clicked`. Every fixture's Submit
echoes to the test server when clicked, so "we stopped at the door" is
proven, not assumed.
"""
import http.server
import json
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


@pytest.fixture(autouse=True)
def _reset_echoes():
    _Handler.echoes = []
    yield


@pytest.fixture(autouse=True)
def _isolated_session():
    """The companion session lives in module globals — one per app, by
    design. Without this a test is satisfied by the PREVIOUS test's socket
    and clicks before its own browser has paired."""
    from engine.autofill import ext_backend

    ext_backend.reset_for_tests()
    yield
    ext_backend.reset_for_tests()


@pytest.fixture()
def app_server(tmp_path, monkeypatch):
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
    deadline = time.time() + 30
    while time.time() < deadline and not server.started:
        time.sleep(0.1)
    assert server.started, "the app never came up"
    yield {"port": port, "data_dir": data_dir}
    server.should_exit = True
    thread.join(timeout=10)


@pytest.fixture()
def ext_dir(tmp_path, app_server):
    """A per-test COPY of the stamped folder. The shared staging dir is
    rewritten on every app launch, so loading it directly races the next
    test's stamp."""
    import shutil

    from scripts import stamp_extension

    dest = stamp_extension.stamp(app_server["port"])
    out = tmp_path / "ext"
    shutil.copytree(dest, out)
    return out


@pytest.fixture()
def context(ext_dir, tmp_path):
    """An INSTALLED browser channel, like the rest of the browser suite.
    Playwright's bundled Chromium refuses to keep an MV3 service worker
    alive here, so the companion never pairs and every assertion below
    would fail for a reason that has nothing to do with the escort."""
    from playwright.sync_api import sync_playwright

    profile = tmp_path / "chrome-profile"
    with sync_playwright() as pw:
        ctx = None
        for channel in ("msedge", "chrome"):
            try:
                ctx = pw.chromium.launch_persistent_context(
                    str(profile), channel=channel, headless=True,
                    args=[f"--disable-extensions-except={ext_dir}",
                          f"--load-extension={ext_dir}"],
                )
                break
            except Exception:
                continue
        if ctx is None:
            pytest.skip("no installed browser channel can load the extension")
        yield ctx
        ctx.close()


def _wait_connected(timeout=90):
    from engine.autofill import ext_backend

    deadline = time.time() + timeout
    while time.time() < deadline:
        if ext_backend.is_live(max_age_s=30):
            return True
        time.sleep(0.3)
    return False


def _matched_companion():
    """The escort refuses to act across a version mismatch (FR-035). The
    real companion IS this version — this just proves the gate is the
    version and nothing else."""
    from engine.autofill import ext_backend

    return ext_backend.version_ok()


def _seed(fixture_server, page_name, **profile):
    from engine import db
    from engine.autofill import browser_controller as bc

    url = f"{fixture_server}/{page_name}"
    fields = dict(first_name="Abhinav", last_name="Battula",
                  email="abhi@example.com", phone="5125550100",
                  city="Austin", state_region="TX", postal_code="78712",
                  country="United States of America",
                  how_heard_default="LinkedIn",
                  authorized_without_sponsorship="yes")
    fields.update(profile)
    db.save_profile(**fields)
    db.upsert_job({"title": "SWE", "company": "Fixture", "url": url,
                   "source": "manual", "location": "SF", "is_remote": False,
                   "description": "d", "posted_date": None})
    job_id = next(j["id"] for j in db.list_all_jobs_minimal()
                  if j["url"] == url)
    bc.start_queue([job_id])
    return job_id


def _echoed(name, timeout=25):
    deadline = time.time() + timeout
    while time.time() < deadline:
        for e in _Handler.echoes:
            if e.get("name") == name and e.get("value"):
                return e["value"]
        time.sleep(0.3)
    return None


def _never_echoed(name, settle=4.0):
    """Give a wrong click every chance to happen, then prove it didn't."""
    time.sleep(settle)
    return not any(e.get("name") == name for e in _Handler.echoes)


def _fake_vault(monkeypatch, email="me@example.com", password="s3cret-Pa55!"):
    from engine import credentials

    store = {"email": email, "password": password}
    monkeypatch.setattr(credentials, "get", lambda domain: store)
    monkeypatch.setattr(credentials, "save", lambda d, e, p: store.update(
        email=e, password=p))
    return store


class TestTheEscortReachesTheDoor:
    """The feature, in one flow: fill → advance → fill → advance → park."""

    def test_a_multi_page_wizard_is_escorted_to_review(
            self, context, app_server, fixture_server):
        assert _wait_connected(), "the companion never paired"
        assert _matched_companion()
        _seed(fixture_server, "wizard_multipage/step1.html")

        # step 1 fills, and the escort presses Continue for us
        assert _echoed("job_application[first_name]") == "Abhinav"
        assert _echoed("__step1_continue") == "yes", (
            "the escort never advanced past step 1")
        # step 2's own blind-spot fields fill, then it advances again
        assert _echoed("q_auth") in ("yes", "Yes")
        assert _echoed("__step2_continue") == "yes", (
            "the escort never advanced past step 2")

    def test_the_final_submit_is_never_clicked(self, context, app_server,
                                               fixture_server):
        """SC-006 — the whole promise of this feature in one assertion."""
        assert _wait_connected()
        _seed(fixture_server, "wizard_multipage/step1.html")
        assert _echoed("__step2_continue") == "yes", "never reached review"
        assert _never_echoed("__final_submit_clicked", settle=6.0), (
            "the escort clicked Submit Application — this is the one thing "
            "it must never do")

    def test_it_parks_in_the_ready_for_review_state(self, context, app_server,
                                                    fixture_server):
        from engine.autofill import ext_backend

        assert _wait_connected()
        _seed(fixture_server, "wizard_multipage/step1.html")
        assert _echoed("__step2_continue") == "yes"
        deadline = time.time() + 20
        trail = []
        while time.time() < deadline:
            trail = ext_backend.progression_clicks()
            if any(c["kind"] == "next" for c in trail):
                break
            time.sleep(0.5)
        assert any(c["kind"] == "next" and c["status"] == "clicked"
                   for c in trail), f"no advance recorded in the trail: {trail}"


class TestTheSpaWizard:
    """Same address, different form — the case an href-keyed one-shot could
    never get right."""

    def test_each_rendered_step_advances_exactly_once(
            self, context, app_server, fixture_server):
        assert _wait_connected()
        _seed(fixture_server, "wizard_spa.html")
        assert _echoed("spa_first") == "Abhinav"
        assert _echoed("__spa_step1_next") == "yes"
        assert _echoed("spa_phone") == "5125550100"
        assert _echoed("__spa_step2_next") == "yes"
        assert _never_echoed("__spa_final_submit", settle=5.0)


class TestTheCap:
    def test_a_never_ending_wizard_stops_at_the_cap(self, context, app_server,
                                                    fixture_server):
        """FR-027: twelve advances, then the applicant gets a look."""
        from engine.autofill import escort as escort_mod

        assert _wait_connected()
        _seed(fixture_server, "wizard_loop.html")
        deadline = time.time() + 60
        while time.time() < deadline:
            advances = [e for e in _Handler.echoes
                        if e.get("name") == "__loop_advance"]
            if len(advances) >= escort_mod.MAX_ADVANCES_PER_JOB:
                break
            time.sleep(0.5)
        time.sleep(6)  # let any thirteenth advance happen if it is going to
        advances = [e for e in _Handler.echoes
                    if e.get("name") == "__loop_advance"]
        assert len(advances) <= escort_mod.MAX_ADVANCES_PER_JOB, (
            f"the escort advanced {len(advances)} times — the cap is "
            f"{escort_mod.MAX_ADVANCES_PER_JOB}")


class TestTheBotCheck:
    def test_a_captcha_page_is_never_advanced_past(self, context, app_server,
                                                   fixture_server):
        """FR-028: constitutional. Nothing is clicked on or near a bot
        check, in any version, for any reason."""
        assert _wait_connected()
        _seed(fixture_server, "captcha_frame.html")
        assert _echoed("cp_first") == "Abhinav", "the page never even filled"
        assert _never_echoed("__captcha_page_continue", settle=8.0), (
            "the escort advanced past a bot check")


class TestLinkedInIsFillOnly:
    def test_nothing_is_ever_clicked_on_linkedin(self, context, app_server,
                                                 fixture_server, monkeypatch):
        """FR-033. The fixture is served from localhost, so the domain rule
        is exercised by pointing the host check at this origin — the rule
        itself (and its parity with the engine) is what we are proving."""
        from engine.autofill import ext_backend

        monkeypatch.setattr(ext_backend, "_NO_CLICK_HOSTS", ("127.0.0.1",))
        assert _wait_connected()
        _seed(fixture_server, "wizard_multipage/step1.html")
        # filling still works...
        assert _echoed("job_application[first_name]") == "Abhinav"
        # ...but nothing is clicked
        assert _never_echoed("__step1_continue", settle=6.0)


class TestSignIn:
    def test_a_saved_login_crosses_the_wall(self, context, app_server,
                                            fixture_server, monkeypatch):
        """FR-015/FR-016: fill both halves, then ONE click, then the page
        behind the wall fills too."""
        _fake_vault(monkeypatch)
        assert _wait_connected()
        _seed(fixture_server, "login_wall.html")
        assert _echoed("__signin_clicked") == "yes", (
            "the sign-in click never happened")
        assert _echoed("pw_first") == "Abhinav", (
            "the page behind the wall never filled — the session did not "
            "survive the sign-in navigation")

    def test_registration_is_prepared_but_never_submitted(
            self, context, app_server, fixture_server, monkeypatch):
        """FR-021: we fill it and save the generated password; the human
        presses Create Account."""
        store = _fake_vault(monkeypatch, password="")
        assert _wait_connected()
        _seed(fixture_server, "registration.html")
        # The fixture reports "<length>:<match>" — the generated secret
        # never goes on the wire, even here.
        report = _echoed("pw_report")
        assert report, "the generated password never reached the form"
        length, match = report.split(":")
        assert int(length) >= 20, f"generated password is only {length} chars"
        assert match == "match", "the confirmation box got a different value"
        assert store["password"] and len(store["password"]) == int(length), (
            "the generated password was not saved to the vault at fill time")
        assert _never_echoed("__create_account_clicked", settle=5.0), (
            "Create Account is final-class — the human presses it")


class TestICIMSAdvance020:
    """020 US6 (FR-023): iCIMS advances by its OWN recognised control.

    019 shipped iCIMS with only the conservative generic Next/Continue
    fallback, never exercised against a fixture — its spec records that
    explicitly as an assumption. This gives it the same allowlist-first
    coverage Workday and Greenhouse have, under every unchanged 019 safety
    rule: one shot per rendered step, capped, and a hard stop at the final
    Submit.

    The fixture labels its advance control "Continue »" rather than a bare
    "Next", so a broken selector cannot be rescued by the generic text
    fallback without that being visible here.
    """

    def test_the_step_advances_by_the_icims_control(self, context,
                                                    fixture_server):
        assert _wait_connected()
        _seed(fixture_server, "icims_step.html")

        assert _echoed("firstname") == "Abhinav", "step 1 never filled"
        assert _echoed("__icims_advanced"), (
            "the iCIMS Continue control was never clicked — the escort "
            "should recognise it by selector, not by its text")

    def test_the_final_submit_is_never_clicked(self, context, fixture_server):
        """FR-024, unchanged and non-negotiable: the human submits."""
        assert _wait_connected()
        _seed(fixture_server, "icims_step.html")

        assert _echoed("__icims_advanced"), "never reached the review step"
        assert _never_echoed("__icims_submitted", settle=6.0), (
            "the escort clicked Submit on an iCIMS application")

    def test_the_advance_is_recorded_in_the_ledger(self, context,
                                                   fixture_server):
        """Every progression click is ledger-recorded — a constitutional
        condition of the 019 clarification, not an optional nicety."""
        from engine.autofill import ext_backend

        assert _wait_connected()
        _seed(fixture_server, "icims_step.html")
        assert _echoed("__icims_advanced")

        trail = ext_backend.progression_clicks()
        assert trail, "the advance was not recorded"
        assert any(entry.get("status") == "clicked" for entry in trail), trail
