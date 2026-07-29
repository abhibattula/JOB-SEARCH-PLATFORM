"""018 The Companion — the REAL widget driven end-to-end (@pytest.mark.browser).

This module exists because of a process failure, not just a code one.

017 shipped a badge button ("Apply with Apply Assist") that did nothing at all:
its handler read `current.posting`, a key the detection code never sets, so it
returned before sending anything. The suite was green throughout, because the
only coverage for that control was::

    assert "apply_here" in self.badge()

A string-presence assertion on a source file proves a string exists. It cannot
prove a control works. Feature 018 makes real-browser interaction coverage a
definition of done for every companion control (spec FR-039), and this file is
where that coverage lives.

The same blindness hid an even older defect: both floating widgets set

    host.style.cssText = "position:fixed;…;top:16px;right:16px;all:initial;"

and `all` is a shorthand for EVERY property, declared last — so it reset
`position` to `static` and the widget rendered at the bottom of the document
flow, off screen, on every page, since v1.0.0.

Harness: the real unpacked extension in real Chromium, `pairing.json` pointed
at a live in-process FastAPI app over the real WebSocket bridge. Controls live
in an OPEN shadow root and are driven through `host.shadowRoot`.
"""
from __future__ import annotations

import http.server
import shutil
import threading
import time
from functools import partial
from pathlib import Path

import pytest

pytestmark = pytest.mark.browser

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "discovery_pages"
EXT_SRC = Path(__file__).resolve().parents[2] / "extension"

# The merged host (018) and the pre-merge badge host, so these tests pass
# across the US1 → US2 transition without being rewritten.
HOST_IDS = ("je-companion-host", "je-discovery-badge-host")

# The primary action's id after the merge, and the badge's id before it.
PRIMARY_IDS = ("primary", "apply")


class _Handler(http.server.SimpleHTTPRequestHandler):
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
    db.save_profile(first_name="Abhinav", last_name="B", email="a@b.com",
                    resume_text="python verilog systemverilog uvm fpga rtl",
                    skills=[])
    db.store_h1b_employers({
        db.normalize_company("Aurora Semiconductors"): {
            "display_name": "Aurora Semiconductors", "approvals": 400,
            "denials": 10, "wage_level_median": None,
            "wage_offered_median": None, "lca_titles": None,
        }
    })

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
    from scripts import stamp_extension

    dest = stamp_extension.stamp(app_server["port"])
    out = tmp_path / "ext"
    shutil.copytree(dest, out)
    return out


@pytest.fixture()
def context(ext_dir, tmp_path):
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


# --------------------------------------------------------------------------
# helpers — every one of them drives the widget the way a person would
# --------------------------------------------------------------------------

def _wait_connected(timeout=15):
    from engine.autofill import ext_backend

    deadline = time.time() + timeout
    while time.time() < deadline:
        if ext_backend.is_live(max_age_s=30):
            return True
        time.sleep(0.3)
    return False


_FIND_HOST_JS = """
(ids) => { for (const id of ids) { if (document.getElementById(id)) return id; }
           return ""; }
"""


def _host_id(page):
    return page.evaluate(_FIND_HOST_JS, list(HOST_IDS))


def _open_and_wait_companion(context, url, timeout=20):
    page = context.new_page()
    page.goto(url)
    page.wait_for_function(
        "(ids) => ids.some(id => document.getElementById(id))",
        arg=list(HOST_IDS), timeout=timeout * 1000)
    return page


def _geometry(page):
    """Computed position + on-screen rect of the companion host."""
    return page.evaluate(
        """(ids) => {
            const id = ids.find(i => document.getElementById(i));
            const h = document.getElementById(id);
            const cs = getComputedStyle(h);
            const r = h.getBoundingClientRect();
            return {
                position: cs.position, display: cs.display,
                zIndex: cs.zIndex,
                top: r.top, left: r.left, bottom: r.bottom, right: r.right,
                width: r.width, height: r.height,
                vh: window.innerHeight, vw: window.innerWidth,
            };
        }""", list(HOST_IDS))


def _on_screen(g):
    """True when the host's rect overlaps the viewport at all."""
    return (g["bottom"] > 0 and g["top"] < g["vh"]
            and g["right"] > 0 and g["left"] < g["vw"]
            and g["width"] > 0 and g["height"] > 0)


def _shadow_text(page):
    return page.evaluate(
        """(ids) => {
            const id = ids.find(i => document.getElementById(i));
            const h = document.getElementById(id);
            return (h && h.shadowRoot) ? h.shadowRoot.textContent : "";
        }""", list(HOST_IDS))


def _click(page, control_ids):
    """Click the first of `control_ids` that exists in the shadow root."""
    clicked = page.evaluate(
        """([ids, controls]) => {
            const id = ids.find(i => document.getElementById(i));
            const root = document.getElementById(id).shadowRoot;
            for (const c of controls) {
                const el = root.getElementById(c);
                if (el) { el.click(); return c; }
            }
            return "";
        }""", [list(HOST_IDS), list(control_ids)])
    assert clicked, f"no control among {control_ids} exists in the companion"
    return clicked


def _primary_label(page):
    return page.evaluate(
        """([ids, controls]) => {
            const id = ids.find(i => document.getElementById(i));
            const root = document.getElementById(id).shadowRoot;
            for (const c of controls) {
                const el = root.getElementById(c);
                if (el) { return (el.textContent || "").trim(); }
            }
            return "";
        }""", [list(HOST_IDS), list(PRIMARY_IDS)])


def _wait_for_session(timeout=20):
    """Poll the app's own queue state until a session is actually running."""
    from engine.autofill import browser_controller as bc

    deadline = time.time() + timeout
    while time.time() < deadline:
        current = bc.current_job()
        if current is not None:
            return current
        time.sleep(0.3)
    return None


# --------------------------------------------------------------------------
# US1 — I can see it, and it does something
# --------------------------------------------------------------------------

class TestCompanionIsVisible:
    """R1: `all:initial` declared LAST reset `position:fixed`, so the widget
    rendered at the end of the document flow — the bottom of the page."""

    def test_it_is_pinned_to_the_viewport(self, context, app_server,
                                          fixture_server):
        assert _wait_connected()
        page = _open_and_wait_companion(
            context, f"{fixture_server}/hostile_css.html")
        g = _geometry(page)
        assert g["position"] == "fixed", (
            "the companion is not pinned — it scrolls away with the document. "
            f"computed position was {g['position']!r}")
        assert _on_screen(g), (
            "the companion rendered off screen on an unscrolled page: "
            f"rect top={g['top']} left={g['left']} vs viewport "
            f"{g['vw']}x{g['vh']}")

    def test_hostile_page_css_cannot_unpin_it(self, context, app_server,
                                              fixture_server):
        """The fixture declares `div { position: static !important }`. An
        inline style without !important loses to that; only an inline
        !important declaration wins."""
        assert _wait_connected()
        page = _open_and_wait_companion(
            context, f"{fixture_server}/hostile_css.html")
        g = _geometry(page)
        assert g["position"] == "fixed"
        assert g["display"] != "none"

    def test_it_stays_on_screen_after_scrolling(self, context, app_server,
                                                fixture_server):
        assert _wait_connected()
        page = _open_and_wait_companion(
            context, f"{fixture_server}/hostile_css.html")
        page.evaluate("() => window.scrollTo(0, document.body.scrollHeight)")
        time.sleep(0.5)
        assert _on_screen(_geometry(page))
        page.evaluate("() => window.scrollTo(0, 0)")
        time.sleep(0.5)
        assert _on_screen(_geometry(page))


class TestPrimaryActionWorks:
    """R2: the launcher was a dead button for the whole of v1.7.0."""

    def test_apply_starts_a_real_session(self, context, app_server,
                                         fixture_server):
        from engine import db

        assert _wait_connected()
        url = f"{fixture_server}/hostile_css.html"
        page = _open_and_wait_companion(context, url)
        page.wait_for_function(
            "(ids) => ids.some(id => { const h = document.getElementById(id);"
            " return h && h.dataset.jeScore; })",
            arg=list(HOST_IDS), timeout=20000)

        _click(page, PRIMARY_IDS)

        current = _wait_for_session()
        assert current is not None, (
            "clicking the primary action started no session — this is the "
            "017 dead-button defect")
        job = db.get_job_by_url(url)
        assert job is not None, "the posting was not recorded"
        assert current["job_id"] == job["id"]

    def test_it_reports_failure_instead_of_going_quiet(self, context,
                                                      app_server,
                                                      fixture_server):
        """FR-010: a control must never appear to have done nothing. With a
        session already running, an ad-hoc fill is refused by the app; the
        companion has to say so and re-enable itself."""
        from engine.autofill import browser_controller as bc

        assert _wait_connected()
        bc.start_queue([])
        with bc._lock:
            bc._state.running = True
            bc._state.backend = "extension"

        page = _open_and_wait_companion(
            context, f"{fixture_server}/bare_application.html")
        _click(page, PRIMARY_IDS)
        deadline = time.time() + 15
        label = ""
        while time.time() < deadline:
            label = _primary_label(page)
            if label and "starting" not in label.lower():
                break
            time.sleep(0.3)
        assert label and "starting" not in label.lower(), (
            f"the primary action is stuck on {label!r} with no outcome shown")


class TestCompanionOnABareApplicationForm:
    """R7: on a Greenhouse `…/application` page there was no widget at all —
    the badge needs posting metadata and the panel needs a running session."""

    def test_it_appears_with_fill_this_page(self, context, app_server,
                                            fixture_server):
        assert _wait_connected()
        page = _open_and_wait_companion(
            context, f"{fixture_server}/bare_application.html")
        assert _on_screen(_geometry(page))
        assert "fill this page" in _shadow_text(page).lower()

    def test_fill_this_page_starts_an_adhoc_session(self, context, app_server,
                                                    fixture_server):
        from engine.autofill.ext_backend import ADHOC_JOB_ID

        assert _wait_connected()
        page = _open_and_wait_companion(
            context, f"{fixture_server}/bare_application.html")
        _click(page, PRIMARY_IDS)
        current = _wait_for_session()
        assert current is not None
        assert current["job_id"] == ADHOC_JOB_ID

    def test_detecting_the_form_stamps_nothing_on_the_page(
            self, context, app_server, fixture_server):
        """The probe must be READ-ONLY. `jeScanner.serialize()` writes
        `data-je-idx` on every field and `data-je-doc` on <html>; calling it
        merely to decide whether to show a widget would mutate every page the
        applicant browses, breaking the 012 read-only guarantee."""
        assert _wait_connected()
        page = _open_and_wait_companion(
            context, f"{fixture_server}/bare_application.html")
        time.sleep(1)
        stamped = page.evaluate(
            "() => document.querySelectorAll('[data-je-idx]').length")
        doc_token = page.evaluate(
            "() => document.documentElement.dataset.jeDoc || ''")
        assert stamped == 0, "detection stamped data-je-idx on the page"
        assert doc_token == "", "detection stamped a doc token on <html>"

    def test_it_does_not_appear_on_an_ordinary_page(self, context, app_server,
                                                    fixture_server):
        """The negative control. A search box, a newsletter and a login are
        not an application — a widget on every such page would be worse than
        the bug it fixes."""
        assert _wait_connected()
        page = context.new_page()
        page.goto(f"{fixture_server}/search_only.html")
        time.sleep(4)
        assert _host_id(page) == "", (
            "the form probe fired on an ordinary page")


class TestCompanionStillTouchesNothing:
    """The standing safety invariant, re-proved on the new fixtures."""

    def test_the_page_is_never_clicked_or_typed_into(self, context, app_server,
                                                     fixture_server):
        assert _wait_connected()
        page = _open_and_wait_companion(
            context, f"{fixture_server}/hostile_css.html")
        time.sleep(1.5)
        assert page.evaluate("() => window.__pageClicked") in (None, False)
        assert page.eval_on_selector("#sentinel-input", "el => el.value") == ""

    def test_nothing_is_ever_submitted(self, context, app_server,
                                       fixture_server):
        assert _wait_connected()
        page = _open_and_wait_companion(
            context, f"{fixture_server}/bare_application.html")
        _click(page, PRIMARY_IDS)
        time.sleep(4)
        assert page.evaluate("() => window.__pageSubmitted") in (None, False)
