"""010 T006: the bridge endpoints — WS auth/supersede/version gate and the
one-time file token. The WS is the only door into fill instructions, so
every failure mode must close with its distinct code."""
import json

import pytest
from starlette.testclient import TestClient, WebSocketDisconnect

from engine import db
from engine.autofill import ext_backend, ext_protocol


@pytest.fixture
def client(tmp_db, monkeypatch):
    monkeypatch.setenv("REFRESH_SYNC", "1")
    from engine import matcher, pipeline

    monkeypatch.setattr(pipeline, "_source_names", lambda: [])
    monkeypatch.setattr(pipeline, "load_companies", lambda: [])
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.setattr(matcher.local_llm, "available", lambda: False)
    from web.main import create_app

    return TestClient(create_app())


def hello_frame(secret=None, version="1.0.0", v=None):
    return json.dumps({
        "v": ext_protocol.PROTOCOL_V if v is None else v,
        "type": "hello", "seq": 1,
        "secret": secret if secret is not None else db.get_bridge_secret(),
        "version": version, "chrome_version": "127",
    })


class TestBridgeInfo:
    def test_info_answers_identity(self, client):
        payload = client.get("/api/bridge/info").json()
        assert payload["app_id"] == "jobengine"
        assert payload["protocol_v"] == ext_protocol.PROTOCOL_V
        assert payload["app_version"]


class TestBridgeAuth:
    def test_correct_secret_gets_hello_ok_and_connects(self, client):
        with client.websocket_connect("/ws/ext") as ws:
            ws.send_text(hello_frame())
            reply = json.loads(ws.receive_text())
            assert reply["type"] == "hello_ok"
            status = ext_backend.status()
            assert status["connected"] is True
            assert status["version"] == "1.0.0"

    def test_wrong_secret_closed_4401(self, client):
        with pytest.raises(WebSocketDisconnect) as excinfo:
            with client.websocket_connect("/ws/ext") as ws:
                ws.send_text(hello_frame(secret="f" * 64))
                ws.receive_text()
        assert excinfo.value.code == 4401
        assert ext_backend.status()["connected"] is False

    def test_wrong_protocol_version_closed_4426(self, client):
        with pytest.raises(WebSocketDisconnect) as excinfo:
            with client.websocket_connect("/ws/ext") as ws:
                ws.send_text(hello_frame(v=99))
                ws.receive_text()
        assert excinfo.value.code == 4426

    def test_newer_session_supersedes_older_4409(self, client):
        with client.websocket_connect("/ws/ext") as first:
            first.send_text(hello_frame())
            assert json.loads(first.receive_text())["type"] == "hello_ok"
            with client.websocket_connect("/ws/ext") as second:
                second.send_text(hello_frame(version="1.0.1"))
                assert json.loads(second.receive_text())["type"] == "hello_ok"
                # the first socket is closed with the supersede code
                with pytest.raises(WebSocketDisconnect) as excinfo:
                    first.receive_text()
                assert excinfo.value.code == 4409
                assert ext_backend.status()["version"] == "1.0.1"


class TestFileToken:
    def test_token_serves_once_then_404(self, client, tmp_path):
        pdf = tmp_path / "resume.pdf"
        pdf.write_bytes(b"%PDF-1.4 fake resume")
        token = ext_backend.issue_file_token(str(pdf))
        first = client.get(f"/api/bridge/file/{token}")
        assert first.status_code == 200
        assert first.content == b"%PDF-1.4 fake resume"
        assert client.get(f"/api/bridge/file/{token}").status_code == 404

    def test_expired_token_404(self, client, tmp_path, monkeypatch):
        pdf = tmp_path / "resume.pdf"
        pdf.write_bytes(b"x")
        token = ext_backend.issue_file_token(str(pdf))
        monkeypatch.setattr(ext_backend, "FILE_TOKEN_TTL", -1.0)
        assert client.get(f"/api/bridge/file/{token}").status_code == 404

    def test_unknown_token_404(self, client):
        assert client.get("/api/bridge/file/deadbeef").status_code == 404
