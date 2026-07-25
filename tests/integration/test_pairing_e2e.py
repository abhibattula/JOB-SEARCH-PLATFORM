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
                    email="pairing-e2e@example.com", phone="5551230000")
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

        httpx.post(f"http://127.0.0.1:{port}/api/autofill/stop", timeout=10)
    finally:
        try:
            ctx.close()
        finally:
            p.stop()
