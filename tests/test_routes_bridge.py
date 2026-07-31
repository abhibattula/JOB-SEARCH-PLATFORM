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
    def test_token_survives_a_retry_within_ttl(self, client, tmp_path):
        # 019 (FR-005): the token used to die on first use, so a transient
        # attach failure turned the retry into http_404 → needs_manual. It
        # now stays redeemable for its TTL; expiry and session-close still
        # kill it (tests below + TestFileTokenRetry019).
        pdf = tmp_path / "resume.pdf"
        pdf.write_bytes(b"%PDF-1.4 fake resume")
        token = ext_backend.issue_file_token(str(pdf))
        first = client.get(f"/api/bridge/file/{token}")
        assert first.status_code == 200
        assert first.content == b"%PDF-1.4 fake resume"
        retry = client.get(f"/api/bridge/file/{token}")
        assert retry.status_code == 200
        assert retry.content == b"%PDF-1.4 fake resume"

    def test_expired_token_404(self, client, tmp_path, monkeypatch):
        pdf = tmp_path / "resume.pdf"
        pdf.write_bytes(b"x")
        token = ext_backend.issue_file_token(str(pdf))
        monkeypatch.setattr(ext_backend, "FILE_TOKEN_TTL", -1.0)
        assert client.get(f"/api/bridge/file/{token}").status_code == 404

    def test_unknown_token_404(self, client):
        assert client.get("/api/bridge/file/deadbeef").status_code == 404


class TestDoctor015:
    """015 (T010/FR-014): one snapshot of the whole pairing chain — and the
    secret NEVER appears on any diagnostic surface."""

    def _write_chain(self, port=8123):
        from engine import paths

        data = paths.data_dir()
        data.mkdir(parents=True, exist_ok=True)
        (data / "port.txt").write_text(str(port), encoding="utf-8")
        (data / "stamp_status.json").write_text(json.dumps({
            "ok": True, "error": None, "at": "2026-07-25T12:00:00",
            "port": port, "app_version": "1.5.0", "copy_warning": None,
        }), encoding="utf-8")
        ext = data / "extension"
        ext.mkdir(parents=True, exist_ok=True)
        (ext / "pairing.json").write_text(json.dumps({
            "port": port, "secret": "s3cr3t-value-abc123",
            "app_id": "jobengine", "protocol_v": 1,
        }), encoding="utf-8")

    def test_doctor_reports_full_chain_and_never_the_secret(self, client, monkeypatch):
        from web import routes_bridge

        self._write_chain(8123)
        monkeypatch.setattr(routes_bridge, "_PROCESS_START_WALL", 0.0)
        resp = client.get("/api/companion/doctor")
        assert resp.status_code == 200
        doc = resp.json()
        assert doc["stamp"]["ok"] is True
        assert doc["pairing"] == {"present": True, "port": 8123,
                                  "protocol_v": 1, "fresh": True}
        assert doc["port"] == {"current": 8123, "match": True}
        assert doc["companion"]["connected"] is False
        assert doc["rejects"]["auth"] == 0
        assert doc["browser"]["preference"] in ("chrome", "msedge", "auto")
        assert "os_default_channel" in doc["browser"]
        assert "s3cr3t-value-abc123" not in resp.text  # FR-014 hard rule

    def test_doctor_flags_stale_pairing_and_port_mismatch(self, client, monkeypatch):
        import time

        from engine import paths
        from web import routes_bridge

        self._write_chain(8123)
        (paths.data_dir() / "port.txt").write_text("9999", encoding="utf-8")
        # the process "started" after pairing was written → pairing is stale
        monkeypatch.setattr(routes_bridge, "_PROCESS_START_WALL",
                            time.time() + 3600)
        doc = client.get("/api/companion/doctor").json()
        assert doc["pairing"]["fresh"] is False
        assert doc["port"] == {"current": 9999, "match": False}

    def test_doctor_degrades_when_files_missing(self, client):
        doc = client.get("/api/companion/doctor").json()
        assert doc["stamp"] is None
        assert doc["pairing"]["present"] is False
        assert doc["port"]["current"] is None
        assert doc["port"]["match"] is False

    def test_companion_browser_reported_from_hello(self, client):
        with client.websocket_connect("/ws/ext") as ws:
            ws.send_text(json.dumps({
                "v": 1, "type": "hello", "seq": 1,
                "secret": db.get_bridge_secret(),
                "version": "1.5.0", "browser": "edge",
            }))
            assert json.loads(ws.receive_text())["type"] == "hello_ok"
            doc = client.get("/api/companion/doctor").json()
            assert doc["companion"]["connected"] is True
            assert doc["companion"]["browser"] == "edge"


class TestRejectRecording015:
    """015 (T010): 4401/4426 closes are counted by kind so the doctor can
    distinguish 'knocking but rejected' from silence."""

    def test_auth_reject_counted(self, client):
        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect("/ws/ext") as ws:
                ws.send_text(hello_frame(secret="f" * 64))
                ws.receive_text()
        assert ext_backend.reject_stats()["auth"] == 1
        assert ext_backend.reject_stats()["last_kind"] == "auth"

    def test_protocol_reject_counted(self, client):
        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect("/ws/ext") as ws:
                ws.send_text(hello_frame(v=99))
                ws.receive_text()
        assert ext_backend.reject_stats()["protocol"] == 1


class TestDoctorCounters016:
    """016 (T010): the doctor exposes the silent-drop tripwires."""

    def test_doctor_includes_dropped_fields_and_scan_errors(self, tmp_db):
        from fastapi.testclient import TestClient

        from engine.autofill import ext_backend
        from web.main import create_app

        ext_backend.record_reject("auth")  # unrelated counters still work
        client = TestClient(create_app())
        doctor = client.get("/api/companion/doctor").json()
        assert doctor["counters"] == {"dropped_fields": 0, "scan_errors": 0,
                                      "version_mismatch_fills": 0}

    def test_doctor_counters_track_drops(self, tmp_db):
        from fastapi.testclient import TestClient

        from engine.autofill import ext_backend, ext_protocol
        from web.main import create_app

        ext_backend.register(lambda m: None, lambda code: None, "1.6.0")
        ext_backend.handle_message(ext_protocol.ScanError(
            tab_id=4, message="TypeError: boom"))
        client = TestClient(create_app())
        doctor = client.get("/api/companion/doctor").json()
        assert doctor["counters"]["scan_errors"] == 1
