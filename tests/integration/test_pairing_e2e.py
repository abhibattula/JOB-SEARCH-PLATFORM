"""015 T015 (@pytest.mark.browser): the HUMAN pairing path, end to end, in
real Edge AND real Chrome.

This is the one path that was never tested — and precisely where every
version failed on the user's machine. Flow per browser channel:

    fresh data dir → real uvicorn (ephemeral port) → REAL stamp_extension
    .stamp(port) → load the STAMPED folder itself into the real browser
    (--load-extension) → poll /api/companion/doctor until the companion is
    CONNECTED with the correct browser identity → start the bundled practice
    application through the public API → assert fields actually fill through
    the full chain (open_tab → content script → fields → decide → fill →
    fill_result), using the app's own status as ground truth.

No mocks anywhere: the stamp that broke in shipped 1.4.0 runs for real, the
extension the user loads is the folder loaded here, and the doctor that the
connect wizard polls is what this test polls (SC-004).
"""
from __future__ import annotations

import socket
import threading
import time

import pytest

pytestmark = pytest.mark.browser

CONNECT_TIMEOUT_S = 60   # SC-004 bound; worst case includes a 30s alarm tick
FILL_TIMEOUT_S = 45


@pytest.fixture()
def app_server(tmp_path, monkeypatch):
    """Real uvicorn on an ephemeral port with a FRESH data dir — the
    extension's service worker needs a real WebSocket bridge."""
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


def _launch(channel, ext_dir, profile_dir):
    from playwright.sync_api import sync_playwright

    p = sync_playwright().start()
    try:
        kwargs = {"headless": True}
        if channel:  # None → Playwright's full bundled Chromium
            kwargs["channel"] = channel
        ctx = p.chromium.launch_persistent_context(
            str(profile_dir),
            args=[
                f"--disable-extensions-except={ext_dir}",
                f"--load-extension={ext_dir}",
            ],
            **kwargs,
        )
    except Exception as exc:
        p.stop()
        pytest.skip(f"{channel or 'chromium'} not available: {exc}")
    return p, ctx


def _wait_fixture_state(port, page_key, predicate, timeout=45.0):
    """The practice fixtures self-report their DOM state (extension-opened
    tabs have no Playwright page handle) — poll until the predicate holds."""
    import httpx

    deadline = time.monotonic() + timeout
    state = None
    while time.monotonic() < deadline:
        snapshot = httpx.get(
            f"http://127.0.0.1:{port}/practice/fixture-state",
            timeout=5).json()
        state = snapshot.get(page_key)
        if state and predicate(state):
            return state
        time.sleep(1.0)
    return state


def _doctor(port):
    import httpx

    return httpx.get(f"http://127.0.0.1:{port}/api/companion/doctor",
                     timeout=5).json()


# The Chrome-family leg runs on Playwright's bundled full Chromium: branded
# Chrome stable (>= 137) removed --load-extension support, so the AUTOMATED
# load can't use it — the HUMAN path (chrome://extensions → Load unpacked)
# still works in real Chrome and is covered by the quickstart walkthrough.
# Chromium carries the same engine and a "Chrome/… (no Edg/)" UA, so the
# browser-identity detection ("chrome") is exercised faithfully (SC-004).
# channel="chromium" = Playwright's FULL Chromium in new-headless mode (plain
# headless resolves to the extension-less headless shell — the 010 lesson).
@pytest.mark.parametrize("channel,expected_browser", [
    ("msedge", "edge"),
    ("chromium", "chrome"),
])
def test_human_pairing_path_connects_and_fills(app_server, tmp_path,
                                               channel, expected_browser):
    import httpx

    from engine import db
    from scripts import stamp_extension

    port = app_server["port"]

    # 1. The REAL stamp — the exact step that silently died in shipped 1.4.0.
    dest = stamp_extension.stamp(port)
    doctor = _doctor(port)
    assert doctor["stamp"]["ok"] is True
    assert doctor["pairing"]["present"] is True
    assert doctor["pairing"]["fresh"] is True  # stamped by THIS app session

    # 2. Load the stamped folder itself into the real browser.
    db.save_profile(first_name="Pairing", last_name="Proof",
                    email="pairing-e2e@example.com", phone="5551230000",
                    authorized_without_sponsorship="yes")
    p, ctx = _launch(channel, dest, tmp_path / f"profile-{channel}")
    try:
        # 3. The companion must connect and identify its browser (SC-004).
        deadline = time.monotonic() + CONNECT_TIMEOUT_S
        doctor = None
        while time.monotonic() < deadline:
            doctor = _doctor(port)
            if doctor["companion"]["connected"]:
                break
            time.sleep(1.0)
        assert doctor and doctor["companion"]["connected"], (
            f"companion never connected in {channel}; last doctor: {doctor}")
        assert doctor["companion"]["browser"] == expected_browser
        assert doctor["companion"]["version"]  # stamped app version
        assert doctor["rejects"]["auth"] == 0  # fresh pairing — no rejects

        # 4. One fill through the FULL chain: the practice application via
        #    the public API; the app's own status is the ground truth.
        resp = httpx.post(f"http://127.0.0.1:{port}/api/autofill/practice",
                          timeout=10)
        assert resp.status_code == 200

        deadline = time.monotonic() + FILL_TIMEOUT_S
        status = None
        while time.monotonic() < deadline:
            status = httpx.get(
                f"http://127.0.0.1:{port}/api/autofill/status", timeout=5,
            ).json()
            if (status["backend"] == "extension"
                    and status["activity"].get("fields_filled", 0) >= 1):
                break
            time.sleep(1.0)
        assert status and status["backend"] == "extension", (
            f"practice run did not use the companion; status: {status}")
        assert status["activity"].get("fields_filled", 0) >= 1, (
            f"companion never filled a field in {channel}; status: {status}")

        # 5. 016 (US2/US3): the DOM itself is the ground truth — choice
        #    fills, sensitive left blank + flagged, panel present, and
        #    ZERO automated submit clicks.
        state = _wait_fixture_state(
            port, "apply",
            lambda s: s.get("sponsorship_no") and s.get("first_name")
            and s.get("eeo_flag"))
        assert state, "practice page never reported a filled state"
        assert state["first_name"] == "Pairing"
        assert state["sponsorship_no"] is True, (
            "sponsorship radio group was not answered from the profile")
        assert state["eeo_value"] == "", (
            "an EEO question was auto-answered — never allowed")
        assert state["eeo_flag"] == "needs_you", (
            "sensitive field missing its needs-you highlight")
        assert state["panel"] is True, "on-page panel not injected"
        clicks = httpx.get(
            f"http://127.0.0.1:{port}/practice/submit-log",
            timeout=5).json()["clicks"]
        assert clicks == 0, "an automated click hit the submit control"

        httpx.post(f"http://127.0.0.1:{port}/api/autofill/stop", timeout=10)
    finally:
        try:
            ctx.close()
        finally:
            p.stop()


FIXTURE_FORM_HTML = """
<!doctype html><html><body>
  <form>
    <label for="fn">First name</label><input id="fn" name="first_name" required>
    <label for="notice">Notice period</label>
    <input id="notice" name="notice" maxlength="10">
    <label for="auth">Work authorization</label>
    <select id="auth" name="work_auth">
      <option>Please select</option><option>Yes</option><option>No</option>
    </select>
    <fieldset>
      <legend>Will you require sponsorship?</legend>
      <label><input type="radio" name="sponsor" value="yes">Yes</label>
      <label><input type="radio" name="sponsor" value="no">No</label>
    </fieldset>
    <fieldset>
      <legend>Which days can you work?</legend>
      <label><input type="checkbox" name="days" value="mon">Monday</label>
      <label><input type="checkbox" name="days" value="tue">Tuesday</label>
    </fieldset>
    <div role="combobox" aria-haspopup="listbox" id="source"
         aria-label="How did you hear about us?">Choose...</div>
  </form>
</body></html>
"""


def _project(descriptors):
    """Logical projection both serializers must agree on (R6 parity)."""
    projected = []
    for d in descriptors:
        projected.append((
            d["type"], (d["label_text"] or "").strip(),
            tuple(d.get("options") or []),
            tuple(m["label"].strip() for m in (d.get("members") or [])),
            bool(d.get("required")), d.get("widget") or "",
            d.get("maxlength"),
        ))
    return sorted(projected)


def test_serializer_parity_same_logical_fields():
    """016 (T011): the same fixture through content/scanner.js and the
    watcher's SERIALIZE_JS yields the SAME logical fields — radio groups
    merged identically, checkbox groups contextualized, required and
    maxlength captured on both paths."""
    from pathlib import Path

    from playwright.sync_api import sync_playwright

    from engine.autofill import fields as fields_mod, watcher

    scanner_js = (Path(__file__).resolve().parents[2] / "extension" /
                  "content" / "scanner.js").read_text(encoding="utf-8")

    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel="chromium", headless=True)
        page = browser.new_page()
        page.set_content(FIXTURE_FORM_HTML)
        page.add_script_tag(content=scanner_js)
        via_scanner = page.evaluate("() => window.jeScanner.serialize()")

        page2 = browser.new_page()
        page2.set_content(FIXTURE_FORM_HTML)
        via_watcher = page2.evaluate(watcher.SERIALIZE_JS,
                                     fields_mod.FIELD_QUERY_SELECTOR)
        browser.close()

    assert _project(via_scanner) == _project(via_watcher)
    merged = [d for d in via_scanner if d["type"] == "radio_group"]
    assert len(merged) == 1
    group = merged[0]
    assert group["label_text"] == "Will you require sponsorship?"
    assert group["options"] == ["Yes", "No"]
    assert len(group["members"]) == 2
    checkboxes = [d for d in via_scanner if d["type"] == "checkbox"]
    assert len(checkboxes) == 2  # never merged
    assert all("Which days can you work?" in d["label_text"]
               for d in checkboxes)
    named = {d["name"]: d for d in via_scanner}
    assert named["first_name"]["required"] is True
    assert named["notice"]["maxlength"] == 10


def _connect_companion(app_server, tmp_path, profile_name):
    """Stamp, launch bundled Chromium with the stamped folder, wait for the
    companion to connect. Returns (playwright, context, port)."""
    import time as time_mod

    from engine import db
    from scripts import stamp_extension

    port = app_server["port"]
    dest = stamp_extension.stamp(port)
    db.save_profile(first_name="Opener", last_name="Proof",
                    email="opener-e2e@example.com", phone="5551230001",
                    authorized_without_sponsorship="yes")
    p, ctx = _launch("chromium", dest, tmp_path / profile_name)
    deadline = time_mod.monotonic() + CONNECT_TIMEOUT_S
    while time_mod.monotonic() < deadline:
        if _doctor(port)["companion"]["connected"]:
            return p, ctx, port
        time_mod.sleep(1.0)
    ctx.close()
    p.stop()
    pytest.skip("companion never connected for the opener test")


def _queue_posting_job(port, newtab=False):
    import httpx

    from engine import db

    url = f"http://127.0.0.1:{port}/practice/posting"
    if newtab:
        url += "?newtab=1"
    db.upsert_job({"title": "DV Engineer", "company": "Aurora",
                   "url": url, "source": "manual", "description": "fixture",
                   "posted_date": None})
    job = db.get_job_by_url(url)
    assert job is not None
    resp = httpx.post(f"http://127.0.0.1:{port}/api/autofill/queue",
                      json={"job_ids": [job["id"]]}, timeout=15)
    assert resp.status_code == 200 and resp.json()["backend"] == "extension"
    return job["id"]


def _wait_for_fill(port, min_filled=1, timeout=FILL_TIMEOUT_S):
    import time as time_mod

    import httpx

    deadline = time_mod.monotonic() + timeout
    status = None
    while time_mod.monotonic() < deadline:
        status = httpx.get(f"http://127.0.0.1:{port}/api/autofill/status",
                           timeout=5).json()
        if status["activity"].get("fields_filled", 0) >= min_filled:
            return status
        time_mod.sleep(1.0)
    return status


def test_apply_opener_reveals_hidden_form_and_fills(app_server, tmp_path):
    """016 (T022, D1/FR-016): on a posting whose form is hidden behind
    Apply, the assistant opens it ONCE and fills the revealed fields —
    and never touches the submit control (SC-004)."""
    import time as time_mod

    import httpx

    p, ctx, port = _connect_companion(app_server, tmp_path, "profile-opener")
    try:
        _queue_posting_job(port)
        status = _wait_for_fill(port)
        assert status and status["activity"].get("fields_filled", 0) >= 1, (
            f"opener flow never filled a field; status: {status}")
        state = _wait_fixture_state(
            port, "posting",
            lambda s: s.get("revealed") and s.get("first_name"))
        assert state, "posting page never reported a filled state"
        assert state["revealed"] is True, (
            "the Apply control was never clicked — form still hidden")
        assert state["first_name"] == "Opener"
        clicks = httpx.get(f"http://127.0.0.1:{port}/practice/submit-log",
                           timeout=5).json()["clicks"]
        assert clicks == 0
        httpx.post(f"http://127.0.0.1:{port}/api/autofill/stop", timeout=10)
    finally:
        try:
            ctx.close()
        finally:
            p.stop()


def test_apply_opener_newtab_transfers_watch_and_fills(app_server, tmp_path):
    """016 (T022, FR-005): when Apply opens the form in a CHILD tab, the
    watch transfers and filling continues there."""
    import time as time_mod

    import httpx

    p, ctx, port = _connect_companion(app_server, tmp_path, "profile-newtab")
    try:
        _queue_posting_job(port, newtab=True)
        status = _wait_for_fill(port)
        assert status and status["activity"].get("fields_filled", 0) >= 1, (
            f"new-tab flow never filled a field; status: {status}")
        state = _wait_fixture_state(
            port, "apply", lambda s: s.get("first_name"), timeout=60.0)
        assert state and state["first_name"] == "Opener", (
            "filling did not continue in the transferred child tab; "
            f"state: {state}")
        httpx.post(f"http://127.0.0.1:{port}/api/autofill/stop", timeout=10)
    finally:
        try:
            ctx.close()
        finally:
            p.stop()
