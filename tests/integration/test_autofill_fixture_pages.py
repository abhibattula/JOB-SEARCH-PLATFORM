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


class TestRichTextFill020:
    """020 US4 (FR-016..FR-019): a rich-text cover letter is seen and written.

    Before this feature these editors matched no selector at all, so the
    highest-value field on the form was not merely unfilled — it was never
    counted, never flagged, and carried no reason. Ground truth here is the
    fixture's own echo, so the assertion is about what actually landed in the
    page, not what the engine believed it wrote.
    """

    ANSWER = "I build embedded systems and want to do it here."

    @pytest.fixture()
    def with_cover_letter(self, profile):
        """A stored answer for the cover-letter question, so the fill has
        something truthful to write (the v1.7.0 contract is unchanged: the
        engine never invents an answer it does not have)."""
        from engine.autofill import answer_bank

        answer_bank.save("Cover Letter", self.ANSWER)
        return profile

    def test_the_editor_is_discovered_and_written(self, with_cover_letter,
                                                  server):
        run_job(f"{server}/richtext_cover_letter.html")
        # the ordinary fields prove the page is being filled at all
        assert wait_for(lambda: {"first_name", "email"} <= set(echoed())), \
            f"echoes: {echoed()}"
        assert wait_for(lambda: "cover_letter" in echoed(), timeout=30), (
            "the rich-text cover letter was never written — before 020 it was "
            f"not even seen. echoes: {echoed()}")
        assert self.ANSWER[:20] in echoed()["cover_letter"]

    def test_the_page_registered_it_as_real_input(self, with_cover_letter,
                                                  server):
        """W1, and the reason this branch exists at all.

        The echo mirror listens for `input`/`change` events. A silent
        textContent write fires neither, so an echo arriving IS the proof
        that a real input event reached the page — which is exactly what
        React, ProseMirror and Quill require before they will keep the value
        instead of re-rendering it away.
        """
        run_job(f"{server}/richtext_cover_letter.html")
        assert wait_for(lambda: "cover_letter" in echoed(), timeout=30), (
            "no input event ever reached the editor — a silent DOM write "
            "would look like this, and a real ATS would discard the text")

    def test_an_editor_placeholder_is_not_mistaken_for_an_answer(
            self, with_cover_letter, server):
        """The Lever shape renders its placeholder as a CHILD node, so a naive
        innerText read sees 'Tell us why…' and concludes the box is already
        answered — the 019 placeholder trap in a new place."""
        from engine.autofill import answer_bank

        answer_bank.save("Why do you want to work here?",
                         "Because of the hardware team.")
        run_job(f"{server}/lever_richtext.html")

        assert wait_for(lambda: "name" in echoed(), timeout=30), \
            f"the page never filled at all: {echoed()}"
        assert wait_for(lambda: "why_editor" in echoed(), timeout=30), (
            "the placeholder was read as an existing answer, so the editor "
            f"was skipped. echoes: {echoed()}")
        assert "Tell us why" not in echoed()["why_editor"]

    def test_a_readonly_editor_is_never_written(self, with_cover_letter, server):
        """contenteditable=false / aria-readonly is display, not input."""
        run_job(f"{server}/lever_richtext.html")
        assert wait_for(lambda: "name" in echoed(), timeout=30)
        time.sleep(2)  # let a few more ticks go by
        assert "locked-note" not in echoed()


class TestCompanionIdleCost020:
    """020 T045/T049: the companion's per-tick cost, kept measurable.

    discovery.js calls scanner.probe() on a timer for the whole time a page
    is open. probe() walks the entire DOM hunting shadow roots and forces
    layout per candidate, so its cost scales with page size. Measured when
    this feature was written (see specs/020-every-job-ranked/baseline.txt):

        4,009 elements ->  2.8 ms      20,009 -> 16.9 ms      60,009 -> 52 ms

    Two corrections that measurement produced, both recorded in research R6:
    the poll is TOP-FRAME ONLY (not per-frame as first claimed), and at
    ordinary page sizes the cost was never the problem it was described as.
    The fix that shipped is a 4x reduction in FREQUENCY, not in per-tick cost.

    The ceiling here is deliberately loose — this is a regression tripwire for
    someone making probe() accidentally quadratic, not a benchmark. A tight
    bound would flake on a loaded CI machine and teach everyone to ignore it.
    """

    CEILING_MS = 60.0

    def test_probe_stays_cheap_on_a_large_form_free_page(self, server):
        from playwright.sync_api import sync_playwright

        scanner = (Path(__file__).resolve().parents[2] / "extension" /
                   "content" / "scanner.js").read_text(encoding="utf-8")

        with sync_playwright() as p:
            browser = None
            for channel in ("msedge", "chrome"):
                try:
                    browser = p.chromium.launch(channel=channel, headless=True)
                    break
                except Exception:
                    continue
            if browser is None:
                pytest.skip("no installed browser channel available")
            page = browser.new_page()
            page.goto(f"{server}/heavy_no_form.html")
            page.wait_for_timeout(300)
            result = page.evaluate(
                "(src) => { eval(src);\n"
                "  const n = document.querySelectorAll('*').length;\n"
                "  const times = [];\n"
                "  for (let i = 0; i < 25; i++) {\n"
                "    const t0 = performance.now();\n"
                "    window.jeScanner.probe();\n"
                "    times.push(performance.now() - t0);\n"
                "  }\n"
                "  times.sort((a, b) => a - b);\n"
                "  return { elements: n, median: times[12] }; }",
                scanner)
            browser.close()

        assert result["elements"] > 3000, "the heavy fixture did not build"
        print(f"\n  probe() median {result['median']:.2f} ms over "
              f"{result['elements']} elements")
        assert result["median"] < self.CEILING_MS, (
            f"probe() median {result['median']:.1f} ms over "
            f"{result['elements']} elements — it was 2.8 ms when 020 measured "
            f"it; something made the scan much more expensive")

    def test_a_form_free_page_is_not_offered_a_fill(self, server):
        """The other half of cheapness: a big ordinary page with one search
        box must not look like an application form."""
        from playwright.sync_api import sync_playwright

        scanner = (Path(__file__).resolve().parents[2] / "extension" /
                   "content" / "scanner.js").read_text(encoding="utf-8")

        with sync_playwright() as p:
            browser = None
            for channel in ("msedge", "chrome"):
                try:
                    browser = p.chromium.launch(channel=channel, headless=True)
                    break
                except Exception:
                    continue
            if browser is None:
                pytest.skip("no installed browser channel available")
            page = browser.new_page()
            page.goto(f"{server}/heavy_no_form.html")
            page.wait_for_timeout(300)
            verdict = page.evaluate(
                "(src) => { eval(src);"
                " const p = window.jeScanner.probe();"
                " return { fields: p.fields, textish: p.textish,"
                "   looks: window.jeScanner.looksLikeApplicationForm(p) }; }",
                scanner)
            browser.close()

        assert verdict["looks"] is False, verdict
