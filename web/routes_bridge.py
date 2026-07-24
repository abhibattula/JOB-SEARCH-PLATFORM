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

from fastapi import APIRouter, WebSocket
from fastapi.responses import FileResponse, JSONResponse
from starlette.concurrency import run_in_threadpool
from starlette.websockets import WebSocketDisconnect

from engine import APP_VERSION, db
from engine.autofill import ext_backend, ext_protocol

log = logging.getLogger(__name__)
router = APIRouter()

PING_INTERVAL_S = 20.0


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
        await websocket.close(code=4401)
        return
    if not isinstance(envelope, dict) or envelope.get("v") != ext_protocol.PROTOCOL_V:
        # wrong protocol generation — reloading the (app-restamped)
        # extension folder is the fix, tell the popup via the close code
        await websocket.close(code=4426)
        return
    try:
        hello = ext_protocol.parse_inbound(raw)
    except ext_protocol.ProtocolError:
        await websocket.close(code=4401)
        return
    if not isinstance(hello, ext_protocol.Hello) or not _secrets.compare_digest(
        hello.secret, db.get_bridge_secret()
    ):
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
        send_threadsafe, close_threadsafe, hello.version
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
