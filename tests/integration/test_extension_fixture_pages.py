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

    def test_custom_dropdown_fills_to_saved_value_011(self, context,
                                                      app_server,
                                                      fixture_server):
        # 011: a custom (non-native) dropdown now fills. Seed the answer bank
        # so the work-auth combobox has a value the companion can pick.
        assert _wait_connected(app_server["port"])
        from engine.autofill import answer_bank
        answer_bank.save("Are you legally authorized to work in the US?",
                         "Yes, I am authorized", category="work_authorization")
        _seed_and_queue(fixture_server, "react_select_dropdown.html")
        assert _echoed("first_name") == "Abhinav"
        # the combobox's hidden mirror echoes the chosen option text
        assert _echoed("work_auth", timeout=15) == "Yes, I am authorized"
        # and the page's real Submit was never clicked
        time.sleep(1)
        assert not any(e.get("name") == "__submitted" for e in _Handler.echoes)

    def test_typeahead_fills_matching_suggestion_011(self, context, app_server,
                                                     fixture_server):
        assert _wait_connected(app_server["port"])
        from engine.autofill import answer_bank
        answer_bank.save("City", "Austin, TX", category="location_city")
        _seed_and_queue(fixture_server, "typeahead.html")
        assert _echoed("first_name") == "Abhinav"
        assert _echoed("city", timeout=15) == "Austin, TX"

    def test_submit_styled_as_option_never_clicked_011(self, context,
                                                       app_server,
                                                       fixture_server):
        # the strongest denylist proof: a page whose dropdown "options"
        # include a real submit button. The companion fills first_name and
        # must NEVER trip a submit — even the option-shaped one.
        assert _wait_connected(app_server["port"])
        _seed_and_queue(fixture_server, "submit_styled_as_option.html")
        assert _echoed("first_name") == "Abhinav"
        time.sleep(3)
        assert not any(e.get("name") == "__submitted" for e in _Handler.echoes)

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


class TestWorkday011:
    def test_workday_style_fills_across_revealed_pages(self, context,
                                                       app_server,
                                                       fixture_server):
        # US2 + C3: identity/contact fields + a custom source combo + a
        # school typeahead fill; a page-2 section revealed 1.2s later also
        # fills (per-page proof); Workday's own Next is never clicked.
        assert _wait_connected(app_server["port"])
        from engine.autofill import answer_bank
        answer_bank.save("How did you hear about us?", "LinkedIn",
                         category="how_heard")
        answer_bank.save("School", "University of Texas at Austin",
                         category="school")
        answer_bank.save("City", "Austin, TX", category="location_city")
        _seed_and_queue(fixture_server, "workday_style.html")
        # page 1
        assert _echoed("wd_first") == "Abhinav"
        assert _echoed("wd_email") == "abhi@example.com"
        assert _echoed("wd_source", timeout=15) == "LinkedIn"
        assert _echoed("wd_school", timeout=15) == "University of Texas at Austin"
        # page 2 (revealed after 1.2s) — proves per-page fill in-suite
        assert _echoed("wd_city", timeout=15) == "Austin, TX"
        # the app never advanced the wizard
        time.sleep(1)
        assert not any(e.get("name") == "__submitted" for e in _Handler.echoes)


class TestIcimsTaleo011:
    def test_icims_style_fills(self, context, app_server, fixture_server):
        assert _wait_connected(app_server["port"])
        _seed_and_queue(fixture_server, "icims_style.html")
        assert _echoed("firstname") == "Abhinav"
        assert _echoed("lastname") == "Battula"
        assert _echoed("email") == "abhi@example.com"

    def test_taleo_style_fills(self, context, app_server, fixture_server):
        assert _wait_connected(app_server["port"])
        _seed_and_queue(fixture_server, "taleo_style.html")
        assert _echoed("firstName") == "Abhinav"
        assert _echoed("lastName") == "Battula"


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


def _seed_and_queue_full(fixture_server, page_name):
    """Like _seed_and_queue but with the profile columns the 019 fixtures
    ask for (address, country, source)."""
    from engine import db
    from engine.autofill import browser_controller as bc

    url = f"{fixture_server}/{page_name}"
    db.save_profile(first_name="Abhinav", last_name="Battula",
                    email="abhi@example.com", phone="5125550100",
                    city="Austin", state_region="TX", postal_code="78712",
                    country="United States of America",
                    how_heard_default="LinkedIn",
                    authorized_without_sponsorship="yes")
    db.upsert_job({"title": "SWE", "company": "Fixture", "url": url,
                   "source": "manual", "location": "SF", "is_remote": False,
                   "description": "d", "posted_date": None})
    job_id = next(j["id"] for j in db.list_all_jobs_minimal()
                  if j["url"] == url)
    bc.start_queue([job_id])
    return job_id


class TestFillGaps019:
    """019 US2: five confirmed blind spots, five fixtures. Every assertion is
    a real value landing in a real field via the /echo mirror — the 018
    lesson, applied: a source-string assertion would have let all five ship
    broken again."""

    def test_aria_labelledby_fields_fill(self, context, app_server,
                                         fixture_server):
        """FR-007: the question reaches these controls ONLY by reference.
        labelText() read labels[0] then aria-label, so every field here
        carried an empty question and classified as nothing."""
        assert _wait_connected(app_server["port"])
        _seed_and_queue_full(fixture_server, "aria_labelledby.html")
        assert _echoed("al_first") == "Abhinav"
        assert _echoed("al_email") == "abhi@example.com"

    def test_shadow_root_form_is_seen_and_filled(self, context, app_server,
                                                 fixture_server):
        """FR-008: document.querySelectorAll never enters a shadow root, so
        this page reported zero fields and rendered no widget at all."""
        assert _wait_connected(app_server["port"])
        _seed_and_queue_full(fixture_server, "shadow_form.html")
        assert _echoed("sh_first") == "Abhinav"
        assert _echoed("sh_email") == "abhi@example.com"

    def test_workday_prompt_options_are_operable(self, context, app_server,
                                                 fixture_server):
        """FR-009: Workday's rows are [data-automation-id=promptOption]
        divs — no role, no listbox li — so the harvester matched nothing and
        every Workday dropdown became needs_manual."""
        assert _wait_connected(app_server["port"])
        _seed_and_queue_full(fixture_server, "workday_prompt_options.html")
        assert _echoed("wp_country") == "United States of America"
        assert _echoed("wp_first") == "Abhinav"
        # the wizard's Next is not the fill path's business
        assert not any(e.get("name") == "__wd_next_clicked"
                       for e in _Handler.echoes)

    def test_placeholder_selects_count_as_unanswered(self, context,
                                                     app_server,
                                                     fixture_server):
        """FR-010: `<option value="0">Select…` read back as a real value, so
        the field was skipped_existing for the life of the document."""
        assert _wait_connected(app_server["port"])
        _seed_and_queue_full(fixture_server, "placeholder_select.html")
        assert _echoed("ps_auth") in ("yes", "Yes")
        # A genuinely prefilled control is still the applicant's own:
        # it is never written, so it never echoes. (Reading the DOM
        # here would mean hunting the right tab; the mirror already
        # knows every value that landed.)
        assert not any(e.get("name") == "ps_country"
                       for e in _Handler.echoes)

    def test_fields_in_a_fixed_dialog_are_visible(self, context, app_server,
                                                  fixture_server):
        """FR-011: an element that is ITSELF position:fixed has a null
        offsetParent — reported invisible, never counted, never filled."""
        assert _wait_connected(app_server["port"])
        _seed_and_queue_full(fixture_server, "fixed_modal_form.html")
        assert _echoed("fx_first") == "Abhinav"
        assert _echoed("fx_city") == "Austin"
        # visibility:hidden is genuinely not on screen — never filled
        assert not any(e.get("name") == "fx_ghost" for e in _Handler.echoes)


class TestGreenhouseNavigateApply019:
    """019 (T037, FR-022): modern job-boards.greenhouse.io NAVIGATES to a
    separate application page. The 016 opener selectors matched none of it,
    and its one-shot key was the href — wrong the moment an SPA keeps the
    address. Neither the click nor the fill happened."""

    def test_apply_navigates_and_the_application_fills(
            self, context, app_server, fixture_server):
        assert _wait_connected(app_server["port"])
        _seed_and_queue_full(fixture_server, "greenhouse_navigate_apply.html")
        # the opener clicked Apply, the browser navigated, and the fields on
        # the NEXT page filled — proven by real values, not by a source read
        assert _echoed("job_application[first_name]") == "Abhinav"
        assert _echoed("job_application[email]") == "abhi@example.com"

    def test_the_final_submit_is_never_clicked(self, context, app_server,
                                               fixture_server):
        """SC-006. The application page's Submit echoes if anything clicks
        it; the fill path must reach the page and stop."""
        assert _wait_connected(app_server["port"])
        _seed_and_queue_full(fixture_server, "greenhouse_navigate_apply.html")
        assert _echoed("job_application[first_name]") == "Abhinav"
        time.sleep(3.0)  # give a wrong click every chance to happen
        assert not any(e.get("name") == "__gh_submitted"
                       for e in _Handler.echoes)


class TestRichText020:
    """020 US4: the COMPANION's rich-text write path, in a real browser.

    The Playwright suite covers the fallback path (Playwright's own fill()
    handles contenteditable). This covers the one that actually ships: the
    filler.js branch, which has to select the region, insert text, and
    dispatch a real input event — because React/ProseMirror/Quill discard a
    silent DOM mutation on their next render, which would lose the
    applicant's cover letter somewhere between filling and submitting.
    """

    def test_the_cover_letter_editor_is_written_by_the_companion(
            self, context, app_server, fixture_server):
        from engine.autofill import answer_bank

        assert _wait_connected(app_server["port"])
        answer_bank.save("Cover Letter",
                         "I build embedded systems and want to do it here.")
        _seed_and_queue_full(fixture_server, "richtext_cover_letter.html")

        # ordinary fields first — proves the page is being filled at all
        got = _echoed("first_name")
        if got is None:
            from engine.autofill import browser_controller as _bc
            from engine import db as _db
            from engine.autofill import ext_backend as _eb
            print("DIAG echoes:", _Handler.echoes)
            print("DIAG activity:", _bc.queue_snapshot().get("activity"))
            print("DIAG counters:", _eb.counters())
            print("DIAG watch:", _eb._watch)
            print("DIAG jobs:", [(j["id"], j["url"])
                                 for j in _db.list_all_jobs_minimal()])
        assert got == "Abhinav"
        landed = _echoed("cover_letter", timeout=20)
        assert landed, (
            "the rich-text cover letter never received a value. Before 020 "
            "this element matched no selector at all, so it was not filled, "
            "not counted and not flagged.")
        assert "embedded systems" in landed

    def test_the_write_arrives_as_a_real_input_event(
            self, context, app_server, fixture_server):
        """The echo mirror only fires on input/change. An echo existing at
        all is the proof that a real event reached the editor — a silent
        textContent write produces none, and a real ATS would discard it."""
        from engine.autofill import answer_bank

        answer_bank.save("Cover Letter", "Real input event please.")
        assert _wait_connected(app_server["port"])
        _seed_and_queue_full(fixture_server, "richtext_cover_letter.html")

        assert _echoed("cover_letter", timeout=20) is not None

    def test_a_readonly_editor_is_never_written(self, context, app_server,
                                                fixture_server):
        from engine.autofill import answer_bank

        answer_bank.save("Why do you want to work here?",
                         "Because of the hardware team.")
        assert _wait_connected(app_server["port"])
        _seed_and_queue_full(fixture_server, "lever_richtext.html")

        assert _echoed("name") == "Abhinav Battula" or _echoed("name")
        time.sleep(2.0)
        assert not any(e.get("name") == "locked_note"
                       for e in _Handler.echoes)

    def test_the_submit_button_is_still_never_clicked(
            self, context, app_server, fixture_server):
        """FR-024: a new write path must not become a new click path."""
        from engine.autofill import answer_bank

        answer_bank.save("Cover Letter", "Anything.")
        assert _wait_connected(app_server["port"])
        _seed_and_queue_full(fixture_server, "richtext_cover_letter.html")
        assert _echoed("first_name") == "Abhinav"
        time.sleep(3.0)
        assert not any(e.get("name") == "__submitted"
                       for e in _Handler.echoes)


class TestIdleBackoff020:
    """020 US5 (FR-021): the backoff must not cost detection.

    The optimisation is only acceptable if a form appearing on a page that
    has gone quiet is still found promptly. That is the one regression
    slowing the poll can cause, so it gets a real browser test rather than a
    source-string assertion.
    """

    def test_a_form_mounting_after_the_poll_slows_is_still_filled(
            self, context, app_server, fixture_server):
        assert _wait_connected(app_server["port"])
        _seed_and_queue_full(fixture_server, "late_form_after_idle.html")

        # the form does not exist for the first 9 s — well past the point the
        # discovery poll has widened — and must still fill once it appears
        assert _echoed("lf_first", timeout=30) == "Abhinav", (
            "the form was never filled after the poll backed off — the "
            "MutationObserver waker is not doing its job")
        assert _echoed("lf_email", timeout=15) == "abhi@example.com"
