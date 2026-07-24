"""012 (Discovery Copilot) — the REAL extension driven end-to-end
(@pytest.mark.browser).

Loads the actual unpacked extension into a real Chromium, points its
pairing.json at a live in-process FastAPI app (real WebSocket bridge), browses
the discovery fixture pages, and asserts the badge renders the right score +
company and that Save persists the job. The badge state is mirrored onto the
host element's `data-je-*` attributes (light DOM), so a closed-world isolated
content script's render is assertable without piercing its shadow root; the
Save button lives in an OPEN shadow root and is driven via the host's
shadowRoot.
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

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "discovery_pages"
EXT_SRC = Path(__file__).resolve().parents[2] / "extension"


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
    # a resume so a real match is produced; a graded employer for sponsorship
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


def _wait_connected(timeout=15):
    from engine.autofill import ext_backend

    deadline = time.time() + timeout
    while time.time() < deadline:
        if ext_backend.is_live(max_age_s=30):
            return True
        time.sleep(0.3)
    return False


def _open_and_wait_badge(context, url, timeout=15):
    page = context.new_page()
    page.goto(url)
    page.wait_for_selector("#je-discovery-badge-host[data-je-score]",
                           timeout=timeout * 1000)
    return page


def _dataset(page):
    return page.eval_on_selector(
        "#je-discovery-badge-host",
        "el => ({...el.dataset})")


class TestDiscoveryBadgeRenders:
    def test_jsonld_badge_shows_score_and_company(self, context, app_server,
                                                  fixture_server):
        assert _wait_connected()
        page = _open_and_wait_badge(context, f"{fixture_server}/jsonld_jobposting.html")
        ds = _dataset(page)
        assert ds.get("jeScore", "").isdigit()
        assert ds.get("jeCompany") == "Aurora Semiconductors"
        # graded employer seeded → a real grade, not "unknown"
        assert ds.get("jeSponsor") not in (None, "", "unknown")

    def test_linkedin_dom_fallback(self, context, app_server, fixture_server):
        assert _wait_connected()
        page = _open_and_wait_badge(context, f"{fixture_server}/linkedin_jobs_view.html")
        ds = _dataset(page)
        assert ds.get("jeScore", "").isdigit()
        assert ds.get("jeCompany") == "Nebula Robotics"

    def test_indeed_dom_fallback(self, context, app_server, fixture_server):
        assert _wait_connected()
        page = _open_and_wait_badge(context, f"{fixture_server}/indeed_viewjob.html")
        ds = _dataset(page)
        assert ds.get("jeScore", "").isdigit()
        assert ds.get("jeCompany") == "Helix Devices"

    def test_no_badge_on_non_posting(self, context, app_server, fixture_server):
        assert _wait_connected()
        page = context.new_page()
        page.set_content("<html><body><h1>Just a blog post</h1></body></html>")
        time.sleep(3)
        assert page.query_selector("#je-discovery-badge-host") is None


class TestDiscoverySave:
    def _save(self, page):
        page.evaluate(
            "() => document.getElementById('je-discovery-badge-host')"
            ".shadowRoot.getElementById('save').click()")

    def test_save_persists_and_dedups(self, context, app_server, fixture_server):
        from engine import db

        assert _wait_connected()
        url = f"{fixture_server}/jsonld_jobposting.html"
        page = _open_and_wait_badge(context, url)
        self._save(page)
        page.wait_for_selector('#je-discovery-badge-host[data-je-saved="1"]',
                               timeout=10000)
        job = db.get_job_by_url(url)
        assert job is not None
        assert job["status"] == "saved" and job["source"] == "manual"
        assert job["title"] == "Design Verification Engineer"

        # reopen the same posting → badge opens already-saved, no duplicate
        page2 = _open_and_wait_badge(context, url)
        page2.wait_for_selector('#je-discovery-badge-host[data-je-saved="1"]',
                                timeout=10000)
        with db._conn() as conn:
            n = conn.execute("SELECT COUNT(*) c FROM jobs WHERE url=?",
                             (url,)).fetchone()["c"]
        assert n == 1


class TestDiscoveryOutOfTheWay:
    def test_dismiss_and_collapse(self, context, app_server, fixture_server):
        assert _wait_connected()
        page = _open_and_wait_badge(context, f"{fixture_server}/linkedin_jobs_view.html")
        # collapse
        page.evaluate(
            "() => document.getElementById('je-discovery-badge-host')"
            ".shadowRoot.getElementById('collapse').click()")
        page.wait_for_selector('#je-discovery-badge-host[data-je-collapsed="1"]',
                               timeout=5000)
        # dismiss removes the badge
        page.evaluate(
            "() => document.getElementById('je-discovery-badge-host')"
            ".shadowRoot.getElementById('dismiss').click()")
        page.wait_for_function(
            "() => !document.getElementById('je-discovery-badge-host')",
            timeout=5000)

    def test_page_is_never_touched(self, context, app_server, fixture_server):
        """Read-only proof in a real browser: after the badge renders, the
        page's own sentinel button was never clicked and its input never
        typed into."""
        assert _wait_connected()
        page = _open_and_wait_badge(context, f"{fixture_server}/jsonld_jobposting.html")
        time.sleep(1)
        assert page.evaluate("() => window.__pageClicked") in (None, False)
        assert page.eval_on_selector("#sentinel-input", "el => el.value") == ""
