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


@pytest.fixture(autouse=True)
def _isolated_companion_session():
    """`ext_backend` keeps the companion session in module-level globals — one
    session per app, by design. The conftest already resets
    `browser_controller` for the same reason; this covers the other half.

    Without it, `_wait_connected` is satisfied by the PREVIOUS test's socket
    (its heartbeat is still inside the freshness window), so a test proceeds
    to click before its own browser has paired, and the session it asks for
    never starts. That reads as a product bug and is not one.
    """
    from engine.autofill import ext_backend

    ext_backend.reset_for_tests()
    yield
    ext_backend.reset_for_tests()


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
    """The card's visible text — NOT `shadowRoot.textContent`, which also
    returns the whole stylesheet and makes any assertion on it meaningless."""
    return page.evaluate(
        """(ids) => {
            const id = ids.find(i => document.getElementById(i));
            const h = document.getElementById(id);
            if (!h || !h.shadowRoot) { return ""; }
            const card = h.shadowRoot.getElementById("card");
            const pill = h.shadowRoot.getElementById("pill");
            return ((card ? card.textContent : "") + " " +
                    (pill ? pill.textContent : ""));
        }""", list(HOST_IDS))


def _panel_notice(page):
    return page.evaluate(
        """(ids) => {
            const id = ids.find(i => document.getElementById(i));
            const h = document.getElementById(id);
            if (!h || !h.shadowRoot) { return "<no host>"; }
            const n = h.shadowRoot.getElementById("notice");
            const p = h.shadowRoot.getElementById("primary");
            return JSON.stringify({
                notice: n ? n.textContent : "",
                primary: p ? p.textContent : "",
                disabled: p ? p.disabled : null,
                session: h.dataset.jeSession,
                detection: h.dataset.jeDetection,
            });
        }""", list(HOST_IDS))


def _app_state():
    from engine.autofill import browser_controller as bc

    with bc._lock:
        return (f"running={bc._state.running} backend={bc._state.backend} "
                f"job_ids={bc._state.job_ids}")


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

class TestContentScriptsParse:
    """A syntax error in ONE content script takes out the whole companion,
    silently: the file never evaluates, `window.jePanel` is never defined, and
    every script after it that touches it dies too. There is no visible
    symptom except that nothing appears — which is indistinguishable from "the
    page isn't a job posting".

    This was not hypothetical. During 018 a CSS comment inside a template
    literal contained backticks, which terminated the literal early; twenty
    tests failed at once with nothing but timeouts to go on, and finding it
    took a hand-rolled console dump. One second of this test would have said
    exactly what was wrong.
    """

    def test_no_script_error_on_any_fixture(self, context, app_server,
                                            fixture_server):
        assert _wait_connected()
        for name in ("hostile_css.html", "bare_application.html",
                     "search_only.html", "framed_application.html"):
            page = context.new_page()
            errors = []
            # `pageerror` is exactly an uncaught exception, which is what a
            # parse failure produces. Console errors are also collected, minus
            # resource-load noise (the fixture server has no favicon).
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.on("console", lambda m: (
                errors.append(m.text)
                if m.type == "error" and "Failed to load resource" not in m.text
                else None))
            page.goto(f"{fixture_server}/{name}")
            time.sleep(2.5)
            page.close()
            assert not errors, f"{name} raised: {errors}"


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


# --------------------------------------------------------------------------
# US2 — One companion, and it looks like a product
# --------------------------------------------------------------------------

def _dataset(page):
    return page.evaluate(
        """(ids) => {
            const id = ids.find(i => document.getElementById(i));
            return id ? {...document.getElementById(id).dataset} : {};
        }""", list(HOST_IDS))


def _host_count(page):
    """Every Job Engine host in the document, however it is named."""
    return page.evaluate(
        """() => document.querySelectorAll(
            '[id^="je-companion"], [id^="je-discovery"]').length""")


def _collapsed(page):
    return _dataset(page).get("jeCollapsed")


def _pill_text(page):
    return page.evaluate(
        """(ids) => {
            const id = ids.find(i => document.getElementById(i));
            const root = document.getElementById(id).shadowRoot;
            const pill = root.getElementById("pill");
            return pill ? (pill.textContent || "").trim() : "";
        }""", list(HOST_IDS))


def _card_visible(page):
    return page.evaluate(
        """(ids) => {
            const id = ids.find(i => document.getElementById(i));
            const root = document.getElementById(id).shadowRoot;
            const card = root.getElementById("card");
            if (!card) { return false; }
            const r = card.getBoundingClientRect();
            return r.width > 0 && r.height > 0;
        }""", list(HOST_IDS))


class TestOneCompanionNotTwo:
    """D1/FR-004: 017 decided one floating widget and shipped two — a badge
    bottom-right and a fill panel top-right, with separate hosts, separate
    shadow roots and no shared state."""

    def test_exactly_one_host_on_a_posting(self, context, app_server,
                                           fixture_server):
        assert _wait_connected()
        page = _open_and_wait_companion(
            context, f"{fixture_server}/hostile_css.html")
        time.sleep(1)
        assert _host_count(page) == 1

    def test_exactly_one_host_during_a_fill(self, context, app_server,
                                            fixture_server):
        assert _wait_connected()
        page = _open_and_wait_companion(
            context, f"{fixture_server}/bare_application.html")
        _click(page, PRIMARY_IDS)
        assert _wait_for_session() is not None
        time.sleep(3)
        assert _host_count(page) == 1, (
            "a second widget appeared once filling started")

    def test_no_companion_in_a_sub_frame(self, context, app_server,
                                         fixture_server):
        assert _wait_connected()
        page = _open_and_wait_companion(
            context, f"{fixture_server}/framed_application.html")
        time.sleep(2)
        assert _host_count(page) == 1
        in_frame = page.evaluate(
            """() => {
                const doc = document.getElementById('embedded').contentDocument;
                if (!doc) { return -1; }
                return doc.querySelectorAll(
                    '[id^="je-companion"], [id^="je-discovery"]').length;
            }""")
        assert in_frame == 0, "a sub-frame mounted its own companion"

    def test_the_merged_host_carries_the_state_mirror(self, context, app_server,
                                                      fixture_server):
        """FR-017: the light-DOM mirror the 012/016/017 suites assert on has
        to survive the merge, on the one remaining host."""
        assert _wait_connected()
        page = _open_and_wait_companion(
            context, f"{fixture_server}/hostile_css.html")
        page.wait_for_function(
            "(ids) => ids.some(id => { const h = document.getElementById(id);"
            " return h && h.dataset.jeScore; })",
            arg=list(HOST_IDS), timeout=20000)
        ds = _dataset(page)
        for key in ("jeScore", "jeBand", "jeCompany", "jeSponsor", "jeSaved",
                    "jeCollapsed", "jeSession", "jeDetection"):
            assert key in ds, f"{key} missing from the merged host"
        assert ds["jeDetection"] in ("posting", "posting+form")


class TestPillAndCard:
    """D2/FR-012–FR-015: it rests small and opens on demand."""

    def test_it_rests_collapsed_and_opens_on_click(self, context, app_server,
                                                   fixture_server):
        assert _wait_connected()
        page = _open_and_wait_companion(
            context, f"{fixture_server}/hostile_css.html")
        time.sleep(1)
        assert _collapsed(page) == "1", "the companion did not rest collapsed"
        assert not _card_visible(page)

        _click(page, ["pill"])
        page.wait_for_function(
            "(ids) => ids.some(id => document.getElementById(id)"
            ".dataset.jeCollapsed === '0')", arg=list(HOST_IDS), timeout=5000)
        assert _card_visible(page)

        _click(page, ["collapse"])
        page.wait_for_function(
            "(ids) => ids.some(id => document.getElementById(id)"
            ".dataset.jeCollapsed === '1')", arg=list(HOST_IDS), timeout=5000)

    def test_the_pill_shows_the_score_when_idle(self, context, app_server,
                                                fixture_server):
        assert _wait_connected()
        page = _open_and_wait_companion(
            context, f"{fixture_server}/hostile_css.html")
        page.wait_for_function(
            "(ids) => ids.some(id => { const h = document.getElementById(id);"
            " return h && h.dataset.jeScore; })",
            arg=list(HOST_IDS), timeout=20000)
        score = _dataset(page)["jeScore"]
        assert score and score in _pill_text(page)

    def test_the_pill_shows_progress_while_filling(self, context, app_server,
                                                   fixture_server):
        assert _wait_connected()
        page = _open_and_wait_companion(
            context, f"{fixture_server}/bare_application.html")
        _click(page, PRIMARY_IDS)
        assert _wait_for_session() is not None
        page.wait_for_function(
            "(ids) => ids.some(id => { const h = document.getElementById(id);"
            " return h && Number(h.dataset.jeSeen || 0) > 0; })",
            arg=list(HOST_IDS), timeout=25000)
        ds = _dataset(page)
        assert "/" in _pill_text(page), (
            f"pill showed {_pill_text(page)!r}, expected filled/seen "
            f"(seen={ds.get('jeSeen')})")

    def test_it_opens_itself_when_a_fill_starts(self, context, app_server,
                                                fixture_server):
        """FR-013: an action must never be missed because the card was shut."""
        assert _wait_connected()
        page = _open_and_wait_companion(
            context, f"{fixture_server}/bare_application.html")
        time.sleep(1)
        assert _collapsed(page) == "1"
        _click(page, PRIMARY_IDS)
        page.wait_for_function(
            "(ids) => ids.some(id => document.getElementById(id)"
            ".dataset.jeCollapsed === '0')", arg=list(HOST_IDS), timeout=20000)

    def test_the_card_stays_inside_a_short_viewport(self, context, app_server,
                                                    fixture_server):
        """FR-015: it must never grow past the screen — that is how 017's
        draft flood made Stop unreachable in the app."""
        assert _wait_connected()
        page = _open_and_wait_companion(
            context, f"{fixture_server}/hostile_css.html")
        page.set_viewport_size({"width": 1280, "height": 500})
        _click(page, ["pill"])
        time.sleep(1)
        g = page.evaluate(
            """(ids) => {
                const id = ids.find(i => document.getElementById(i));
                const r = document.getElementById(id).getBoundingClientRect();
                return {top: r.top, bottom: r.bottom, height: r.height,
                        vh: window.innerHeight};
            }""", list(HOST_IDS))
        assert g["height"] <= g["vh"], (
            f"the card is {g['height']}px tall in a {g['vh']}px viewport")
        assert g["top"] >= 0 and g["bottom"] <= g["vh"] + 1


def _primary_for(page, session, detection):
    """Run the panel's OWN `primaryFor` against a state pair.

    The function is pure, so every combination can be covered without staging
    nine live sessions. It cannot be reached as `window.jePanel.primaryFor`
    from here: content scripts run in an isolated world with a separate JS
    heap, so a page-context `evaluate` sees nothing they define. (The host
    ELEMENT is shared, which is why the dataset mirror and shadowRoot clicks
    work — but expando properties are not.) So the shipped source is sliced
    out of panel.js and evaluated as-is: the real code, really executed.
    """
    src = (EXT_SRC / "content" / "panel.js").read_text(encoding="utf-8")
    start = src.index("function primaryFor(")
    depth, i = 0, src.index("{", start)
    while True:
        if src[i] == "{":
            depth += 1
        elif src[i] == "}":
            depth -= 1
            if depth == 0:
                break
        i += 1
    fn = src[start:i + 1]
    return page.evaluate(
        "([s, d]) => { " + fn + " return primaryFor(s, d); }",
        [session, detection])


class TestCompanionIsUsableByKeyboard:
    """FR-018: reachable and operable without a mouse, with a visible focus
    ring. A floating widget that can only be poked at is a widget half the
    people who need it cannot use."""

    def test_the_pill_opens_on_enter(self, context, app_server,
                                     fixture_server):
        assert _wait_connected()
        page = _open_and_wait_companion(
            context, f"{fixture_server}/hostile_css.html")
        time.sleep(1)
        assert _collapsed(page) == "1"
        page.evaluate(
            """(ids) => {
                const id = ids.find(i => document.getElementById(i));
                const pill = document.getElementById(id).shadowRoot
                    .getElementById("pill");
                pill.focus();
                pill.dispatchEvent(new KeyboardEvent("keydown",
                    {key: "Enter", bubbles: true}));
            }""", list(HOST_IDS))
        page.wait_for_function(
            "(ids) => ids.some(id => document.getElementById(id)"
            ".dataset.jeCollapsed === '0')", arg=list(HOST_IDS), timeout=5000)

    FOCUS_JS = """
        ([ids, controls]) => {
            const id = ids.find(i => document.getElementById(i));
            const root = document.getElementById(id).shadowRoot;
            const bad = [];
            for (const c of controls) {
                const el = root.getElementById(c);
                if (!el) { bad.push(c + ":missing"); continue; }
                el.focus();
                if (root.activeElement !== el) { bad.push(c); }
            }
            return bad;
        }"""

    def test_every_control_is_focusable(self, context, app_server,
                                        fixture_server):
        """Checked in each state separately: whichever of pill and card is
        showing owns the focus order, and the other is `hidden` — which
        correctly cannot take focus."""
        assert _wait_connected()
        page = _open_and_wait_companion(
            context, f"{fixture_server}/hostile_css.html")
        time.sleep(1)

        collapsed_bad = page.evaluate(self.FOCUS_JS, [list(HOST_IDS), ["pill"]])
        assert collapsed_bad == [], f"pill not reachable: {collapsed_bad}"

        _click(page, ["pill"])
        time.sleep(0.5)
        expanded_bad = page.evaluate(
            self.FOCUS_JS,
            [list(HOST_IDS), ["collapse", "dismiss", "primary", "save"]])
        assert expanded_bad == [], f"not keyboard-reachable: {expanded_bad}"

    def test_focus_is_visible(self, context, app_server, fixture_server):
        assert _wait_connected()
        page = _open_and_wait_companion(
            context, f"{fixture_server}/hostile_css.html")
        outline = page.evaluate(
            """(ids) => {
                const id = ids.find(i => document.getElementById(i));
                const root = document.getElementById(id).shadowRoot;
                for (const sheet of root.styleSheets) {
                    for (const rule of sheet.cssRules) {
                        if ((rule.selectorText || "").includes("focus-visible")) {
                            return rule.style.outline || rule.style.outlineWidth;
                        }
                    }
                }
                return "";
            }""", list(HOST_IDS))
        assert outline, "no :focus-visible outline is defined"


class TestPrimaryActionStateMachine:
    """FR-007: exactly one primary action, whose label and behaviour follow
    the state. Driven through the pure function the panel exports, so every
    combination is covered without staging each one in a live session."""

    CASES = [
        # session,     detection,       action,           label fragment
        ("idle",       "posting",       "apply",          "apply assist"),
        ("idle",       "posting+form",  "apply",          "apply assist"),
        ("idle",       "form",          "fill_here",      "fill this page"),
        ("starting",   "posting",       "",               "starting"),
        ("starting",   "form",          "",               "starting"),
        ("filling",    "posting",       "stop",           "stop"),
        ("filling",    "form",          "stop",           "stop"),
        ("stopped",    "posting",       "fill_again",     "fill again"),
        ("done",       "form",          "fill_again",     "fill again"),
    ]

    def test_every_state_maps_to_one_action(self, context, app_server,
                                            fixture_server):
        assert _wait_connected()
        page = _open_and_wait_companion(
            context, f"{fixture_server}/hostile_css.html")
        for session, detection, action, fragment in self.CASES:
            got = _primary_for(page, session, detection)
            assert got["action"] == action, (
                f"{session}/{detection}: expected action {action!r}, "
                f"got {got['action']!r}")
            assert fragment in got["label"].lower(), (
                f"{session}/{detection}: label {got['label']!r} does not "
                f"contain {fragment!r}")
            assert got["disabled"] is (session == "starting")


# --------------------------------------------------------------------------
# US3 — Every answer, readable, insertable, correctable
# --------------------------------------------------------------------------

def _answer_rows(page):
    """Every rendered answer row, with the state the panel is showing."""
    return page.evaluate(
        """(ids) => {
            const id = ids.find(i => document.getElementById(i));
            const root = document.getElementById(id).shadowRoot;
            return Array.from(root.querySelectorAll(".qa")).map(el => ({
                key: el.dataset.jeKey || "",
                state: el.dataset.jeState || "",
                group: (el.closest("[data-je-group]") || {}).dataset
                    ? el.closest("[data-je-group]").dataset.jeGroup : "",
                question: (el.querySelector(".q") || {}).textContent || "",
                answer: (el.querySelector(".a") || {}).textContent || "",
                buttons: Array.from(el.querySelectorAll(".sm"))
                    .filter(b => !b.hidden)
                    .map(b => b.textContent),
                askable: !(el.querySelector(".ask") || {hidden: true}).hidden,
            }));
        }""", list(HOST_IDS))


def _expand_all_groups(page):
    page.evaluate(
        """(ids) => {
            const id = ids.find(i => document.getElementById(i));
            const root = document.getElementById(id).shadowRoot;
            root.querySelectorAll(".grph").forEach(h => {
                if (h.getAttribute("aria-expanded") !== "true") { h.click(); }
            });
        }""", list(HOST_IDS))


def _wait_for_feed_to_settle(page, quiet_for=3.0, timeout=40.0):
    """Wait until the answer count stops moving.

    Fields are decided incrementally — a fill goes out the moment it is
    decided, and the drafter answers slowly — so the first payload carries
    only part of the form. Asserting on `jeAnswers > 0` catches the feed
    mid-flight and makes every assertion about its contents a coin toss.
    """
    deadline = time.time() + timeout
    last, stable_since = -1, time.time()
    while time.time() < deadline:
        now = int(_dataset(page).get("jeAnswers") or 0)
        if now != last:
            last, stable_since = now, time.time()
        elif now > 0 and time.time() - stable_since >= quiet_for:
            return now
        time.sleep(0.4)
    return last


def _fill_the_bare_form(context, fixture_server):
    """Start an ad-hoc fill on the metadata-less application fixture and wait
    until the companion has answers to show."""
    assert _wait_connected(), "the companion never paired with the app"
    page = _open_and_wait_companion(
        context, f"{fixture_server}/bare_application.html")
    # A disabled button swallows .click() silently, so wait for the primary
    # action to actually be live before pressing it.
    page.wait_for_function(
        """([ids, controls]) => {
            const id = ids.find(i => document.getElementById(i));
            if (!id) { return false; }
            const root = document.getElementById(id).shadowRoot;
            for (const c of controls) {
                const el = root.getElementById(c);
                if (el) { return !el.disabled; }
            }
            return false;
        }""", arg=[list(HOST_IDS), list(PRIMARY_IDS)], timeout=20000)
    _click(page, PRIMARY_IDS)
    assert _wait_for_session() is not None, (
        f"no fill session started. panel={_panel_notice(page)} "
        f"app={_app_state()}")
    page.wait_for_function(
        "(ids) => ids.some(id => { const h = document.getElementById(id);"
        " return h && Number(h.dataset.jeAnswers || 0) > 0; })",
        arg=list(HOST_IDS), timeout=30000)
    _wait_for_feed_to_settle(page)
    _expand_all_groups(page)
    return page


class TestEveryAnswerIsOnThePage:
    def test_profile_filled_fields_are_listed(self, context, app_server,
                                              fixture_server):
        """R5: v1.7.0 listed ONLY questions the AI drafter touched. Name and
        email were filled on the page and absent from the panel, so the
        review surface could not be used to review the application."""
        page = _fill_the_bare_form(context, fixture_server)
        rows = _answer_rows(page)
        questions = " | ".join(r["question"] for r in rows)
        assert "First Name" in questions, (
            f"profile-filled fields missing from the panel: {questions}")
        assert any(r["group"] == "profile" for r in rows)

    def test_answers_are_grouped_with_counts(self, context, app_server,
                                             fixture_server):
        page = _fill_the_bare_form(context, fixture_server)
        groups = page.evaluate(
            """(ids) => {
                const id = ids.find(i => document.getElementById(i));
                const root = document.getElementById(id).shadowRoot;
                return Array.from(root.querySelectorAll("[data-je-group]"))
                    .filter(s => !s.hidden)
                    .map(s => ({
                        group: s.dataset.jeGroup,
                        label: s.querySelector(".grph").textContent,
                    }));
            }""", list(HOST_IDS))
        assert groups, "no answer groups rendered"
        for g in groups:
            assert "(" in g["label"], f"group {g['group']} shows no count"
        # needs-you always renders before the rest
        ids_in_order = [g["group"] for g in groups]
        if "needs_you" in ids_in_order:
            assert ids_in_order.index("needs_you") == 0

    def test_every_answer_offers_copy_and_insert(self, context, app_server,
                                                 fixture_server):
        """R4: Insert and Show me are gated on `je_idx`, which the feed never
        carried — so through all of v1.7.0 only Copy ever rendered."""
        page = _fill_the_bare_form(context, fixture_server)
        answered = [r for r in _answer_rows(page) if r["answer"]]
        assert answered, "no answered rows to check"
        for row in answered:
            assert "Copy" in row["buttons"], row
            assert "Insert" in row["buttons"], (
                f"Insert never rendered for {row['question']!r} — the feed "
                "carries no field id")
            assert "Show me" in row["buttons"], row


class TestInsertAndShowMe:
    def test_insert_fills_exactly_one_field(self, context, app_server,
                                            fixture_server):
        """FR-023: Insert writes to the ONE field the applicant chose, and
        touches nothing else on the page."""
        page = _fill_the_bare_form(context, fixture_server)
        # a sentinel in a neighbouring field must survive untouched
        page.evaluate(
            "() => { document.getElementById('school').value = 'SENTINEL'; }")

        # Take a row from the profile group: those carry short, exact values
        # (a name, an email), so "did this land in that field" is unambiguous.
        chosen = page.evaluate(
            """(ids) => {
                const id = ids.find(i => document.getElementById(i));
                const root = document.getElementById(id).shadowRoot;
                const group = root.querySelector('[data-je-group="profile"]');
                if (!group) { return null; }
                for (const el of group.querySelectorAll(".qa")) {
                    const insert = Array.from(el.querySelectorAll(".sm"))
                        .find(b => b.textContent === "Insert" && !b.hidden);
                    const a = el.querySelector(".a");
                    const field = document.querySelector(
                        '[data-je-idx="' + (el.dataset.jeIdx || "") + '"]');
                    if (!insert || !a || !a.textContent) { continue; }
                    const target = Array.from(
                        document.querySelectorAll("[data-je-idx]"))
                        .find(f => f.value === a.textContent);
                    if (!target) { continue; }
                    target.value = "";
                    insert.click();
                    return {answer: a.textContent,
                            idx: target.getAttribute("data-je-idx")};
                }
                return null;
            }""", list(HOST_IDS))
        if not chosen:
            pytest.skip("no profile-filled row to insert on this run")

        page.wait_for_function(
            "(c) => { const el = document.querySelector("
            "'[data-je-idx=\"' + c.idx + '\"]'); "
            "return el && el.value === c.answer; }",
            arg=chosen, timeout=10000)
        assert page.eval_on_selector(
            "#school", "el => el.value") == "SENTINEL"

    def test_show_me_scrolls_the_field_into_view(self, context, app_server,
                                                 fixture_server):
        page = _fill_the_bare_form(context, fixture_server)
        page.set_viewport_size({"width": 1000, "height": 400})
        page.evaluate("() => window.scrollTo(0, 0)")
        moved = page.evaluate(
            """(ids) => {
                const id = ids.find(i => document.getElementById(i));
                const root = document.getElementById(id).shadowRoot;
                const before = window.scrollY;
                const rows = Array.from(root.querySelectorAll(".qa"));
                const last = rows[rows.length - 1];
                const jump = last && Array.from(last.querySelectorAll(".sm"))
                    .find(b => b.textContent === "Show me" && !b.hidden);
                if (!jump) { return null; }
                jump.click();
                return before;
            }""", list(HOST_IDS))
        if moved is None:
            pytest.skip("no jumpable row on this fixture run")
        time.sleep(1.5)
        assert page.evaluate("() => window.scrollY") != moved


class TestTypingIsNeverDestroyed:
    """R6: `setAnswers` did `list.textContent = ""` and rebuilt every row,
    while the app pushed a new payload on EVERY scan — a MutationObserver plus
    a 2 s safety poll. A half-typed answer was wiped before Enter could be
    pressed, which made 017's ask-once capture close to unusable."""

    def test_typed_text_and_focus_survive_several_scans(self, context,
                                                        app_server,
                                                        fixture_server):
        page = _fill_the_bare_form(context, fixture_server)
        typed = page.evaluate(
            """(ids) => {
                const id = ids.find(i => document.getElementById(i));
                const root = document.getElementById(id).shadowRoot;
                const input = Array.from(root.querySelectorAll(".ask"))
                    .find(i => !i.hidden && !i.disabled);
                if (!input) { return null; }
                input.focus();
                input.value = "May 1st 2027";
                return true;
            }""", list(HOST_IDS))
        if not typed:
            pytest.skip("no needs-you row on this fixture run")

        # three scan cycles: the safety poll is 2 s
        time.sleep(7)

        after = page.evaluate(
            """(ids) => {
                const id = ids.find(i => document.getElementById(i));
                const root = document.getElementById(id).shadowRoot;
                const input = Array.from(root.querySelectorAll(".ask"))
                    .find(i => i.value === "May 1st 2027");
                return {
                    present: !!input,
                    value: input ? input.value : "",
                    focused: !!input && root.activeElement === input,
                };
            }""", list(HOST_IDS))
        assert after["present"], "the input the applicant was typing into was destroyed"
        assert after["value"] == "May 1st 2027"
        assert after["focused"], "focus was stolen by a re-render"


# --------------------------------------------------------------------------
# US4 — Full control without switching to the app
# --------------------------------------------------------------------------

class TestSessionControlFromThePage:
    """FR-030/FR-033: 017 put a sticky Stop on the APP's page. Stopping a run
    still meant leaving the application you were filling to go and find the
    app window — which is exactly the to-and-fro this feature removes."""

    def test_stop_actually_stops_the_queue(self, context, app_server,
                                           fixture_server):
        from engine.autofill import browser_controller as bc

        page = _fill_the_bare_form(context, fixture_server)
        assert bc.current_job() is not None

        label = _primary_label(page)
        assert "stop" in label.lower(), (
            f"the primary action should be Stop while filling, got {label!r}")
        _click(page, PRIMARY_IDS)

        deadline = time.time() + 15
        while time.time() < deadline:
            if bc.current_job() is None:
                break
            time.sleep(0.3)
        assert bc.current_job() is None, "Stop did not stop the app's queue"

    def test_an_app_refusal_is_shown_on_the_page(self, context, app_server,
                                                 fixture_server):
        """FR-033: the refusal used to be stored for the toolbar popup only —
        a surface the applicant has no reason to open."""
        assert _wait_connected()
        first = _fill_the_bare_form(context, fixture_server)
        assert first is not None

        second = _open_and_wait_companion(
            context, f"{fixture_server}/bare_application.html")
        _click(second, PRIMARY_IDS)
        deadline = time.time() + 15
        notice = ""
        while time.time() < deadline:
            notice = second.evaluate(
                """(ids) => {
                    const id = ids.find(i => document.getElementById(i));
                    const n = document.getElementById(id).shadowRoot
                        .getElementById("notice");
                    return n && !n.hidden ? n.textContent : "";
                }""", list(HOST_IDS))
            if notice:
                break
            time.sleep(0.4)
        assert notice, "the app's refusal never reached the page"


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
