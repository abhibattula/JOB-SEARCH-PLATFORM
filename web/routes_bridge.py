"""Bridge endpoints (feature 010): the WebSocket the browser companion
connects to, plus identity probe and one-time resume-file fetch.

Close codes (contracts/bridge-protocol.md):
  4401 bad/missing secret or malformed hello
  4409 superseded by a newer companion session
  4426 protocol version mismatch (user must reload the extension)
"""
from __future__ import annotations

import asyncio
import json
import logging
import secrets as _secrets
import time

from fastapi import APIRouter, WebSocket
from fastapi.responses import FileResponse, JSONResponse
from starlette.concurrency import run_in_threadpool
from starlette.websockets import WebSocketDisconnect

from engine import APP_VERSION, db
from engine.autofill import ext_backend, ext_protocol

log = logging.getLogger(__name__)
router = APIRouter()

PING_INTERVAL_S = 20.0

# 015 (FR-014): pairing freshness = "was pairing.json stamped by THIS app
# process's launch?" — this module imports once at startup, so its import
# time is the process-start reference.
_PROCESS_START_WALL = time.time()

# 020: the slack was 1 s and that is too tight to be true. desktop.py stamps
# the extension BEFORE it imports web.main, and stamping copies the whole
# extension folder — so on a slow or loaded disk pairing.json is legitimately
# written more than a second before this module is imported, and a perfectly
# good launch reported itself stale. It cost a false smoke failure on 2.0.0.
#
# The check's real intent is "not left over from a PREVIOUS session", and
# those files are minutes or hours old, so a generous window keeps the
# meaning while tolerating a slow copy.
_STAMP_SLACK_S = 120.0


@router.get("/api/bridge/info")
def bridge_info() -> dict:
    """Unauthenticated identity probe the service worker uses before
    presenting the secret."""
    return {
        "app_id": "jobengine",
        "app_version": APP_VERSION,
        "protocol_v": ext_protocol.PROTOCOL_V,
    }


@router.get("/api/bridge/file/{token}")
def bridge_file(token: str):
    path = ext_backend.consume_file_token(token)
    if path is None:
        return JSONResponse({"detail": "unknown or expired token"}, status_code=404)
    try:
        return FileResponse(path)
    except Exception:
        return JSONResponse({"detail": "file unavailable"}, status_code=404)


@router.get("/api/companion/doctor")
def companion_doctor() -> dict:
    """015 (FR-014): one snapshot of the entire pairing chain, composed from
    engine seams — powers the connect wizard, the diagnostics section, the
    frozen smoke gate, and the E2E test. Degrades to nulls/False instead of
    erroring; the pairing SECRET is never included (booleans/ports only)."""
    from engine import paths, settings as settings_mod
    from engine.autofill import default_browser

    data = paths.data_dir()

    stamp = None
    stamp_path = data / "stamp_status.json"
    if stamp_path.exists():
        try:
            stamp = json.loads(stamp_path.read_text(encoding="utf-8"))
        except Exception:
            stamp = {"ok": False, "error": "stamp_status.json unreadable",
                     "at": None, "port": None, "app_version": None,
                     "copy_warning": None}
    stamp = stamp if stamp is None else {k: stamp.get(k) for k in
                                         ("ok", "error", "at", "port",
                                          "app_version", "copy_warning")}

    pairing = {"present": False, "port": None, "protocol_v": None,
               "fresh": False}
    pairing_path = data / "extension" / "pairing.json"
    if pairing_path.exists():
        pairing["present"] = True
        try:
            pdata = json.loads(pairing_path.read_text(encoding="utf-8"))
            pairing["port"] = pdata.get("port")
            pairing["protocol_v"] = pdata.get("protocol_v")
            pairing["fresh"] = (
                pairing_path.stat().st_mtime
                >= _PROCESS_START_WALL - _STAMP_SLACK_S
            )
        except Exception:
            log.debug("pairing.json unreadable for doctor", exc_info=True)

    current_port = None
    port_path = data / "port.txt"
    if port_path.exists():
        try:
            current_port = int(port_path.read_text(encoding="utf-8").strip())
        except (ValueError, OSError):
            current_port = None
    port_match = bool(current_port is not None
                      and pairing["port"] == current_port)

    preference = settings_mod.get("PREFERRED_BROWSER") or "chrome"
    os_default = default_browser.default_channel_order()[0]

    return {
        "stamp": stamp,
        "pairing": pairing,
        "port": {"current": current_port, "match": port_match},
        "companion": ext_backend.status(),
        # 019 (FR-001): the app and companion ship as one version and the
        # check is exact. A stale bundle connects happily and silently
        # withholds fills, so the connect page must be able to go amber.
        "app_version": APP_VERSION,
        "version_ok": ext_backend.version_ok(),
        "rejects": ext_backend.reject_stats(),
        # 016 (T010): silent-drop tripwires — wrong-tab fields + content-
        # script scan failures are counted, never invisible.
        "counters": ext_backend.counters(),
        "browser": {
            "os_default_channel": os_default,
            "preference": preference,
            # D3/FR-019: Auto IS the OS default — no mismatch possible there
            "mismatch": preference != "auto" and os_default != preference,
        },
    }


@router.websocket("/ws/ext")
async def ws_ext(websocket: WebSocket) -> None:
    await websocket.accept()

    # --- handshake: first frame must be a valid, authenticated hello ---
    try:
        raw = await websocket.receive_text()
    except WebSocketDisconnect:
        return
    try:
        envelope = json.loads(raw)
    except ValueError:
        ext_backend.record_reject("auth")  # 015: malformed hello counts as 4401
        await websocket.close(code=4401)
        return
    if not isinstance(envelope, dict) or envelope.get("v") != ext_protocol.PROTOCOL_V:
        # wrong protocol generation — reloading the (app-restamped)
        # extension folder is the fix, tell the popup via the close code
        ext_backend.record_reject("protocol")
        await websocket.close(code=4426)
        return
    try:
        hello = ext_protocol.parse_inbound(raw)
    except ext_protocol.ProtocolError:
        ext_backend.record_reject("auth")
        await websocket.close(code=4401)
        return
    if not isinstance(hello, ext_protocol.Hello) or not _secrets.compare_digest(
        hello.secret, db.get_bridge_secret()
    ):
        ext_backend.record_reject("auth")
        await websocket.close(code=4401)
        return

    loop = asyncio.get_running_loop()

    def send_threadsafe(payload: dict) -> None:
        asyncio.run_coroutine_threadsafe(
            websocket.send_text(json.dumps(payload)), loop
        )

    def close_threadsafe(code: int) -> None:
        asyncio.run_coroutine_threadsafe(websocket.close(code=code), loop)

    superseded_close = ext_backend.register(
        send_threadsafe, close_threadsafe, hello.version,
        browser=hello.browser,
    )
    if superseded_close is not None:
        try:
            superseded_close(4409)
        except Exception:  # the old socket may already be gone
            log.debug("closing superseded companion failed", exc_info=True)

    await websocket.send_text(json.dumps(
        ext_protocol.outbound("hello_ok", session=_secrets.token_hex(8),
                              app_version=APP_VERSION)
    ))

    async def ping_forever() -> None:
        while True:
            await asyncio.sleep(PING_INTERVAL_S)
            await websocket.send_text(json.dumps(ext_protocol.outbound("ping")))

    ping_task = asyncio.create_task(ping_forever())
    try:
        while True:
            raw = await websocket.receive_text()
            try:
                msg = ext_protocol.parse_inbound(raw)
            except ext_protocol.ProtocolError:
                log.debug("dropped malformed companion message")
                continue
            # engine-side processing may take locks / hit SQLite — keep it
            # off the event loop
            await run_in_threadpool(ext_backend.handle_message, msg)
    except WebSocketDisconnect:
        pass
    finally:
        ping_task.cancel()
        ext_backend.unregister(send_threadsafe)
