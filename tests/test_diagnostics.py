"""005-T020: GET /api/diagnostics/local-llm-selftest — a real inference call,
not just an import check (packaging/smoke_test.py depends on this route
returning a genuine model reply, not merely HTTP 200)."""
import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(tmp_db, monkeypatch):
    monkeypatch.setenv("REFRESH_SYNC", "1")
    from engine import pipeline

    monkeypatch.setattr(pipeline, "_source_names", lambda: [])
    monkeypatch.setattr(pipeline, "load_companies", lambda: [])
    from web.main import create_app

    return TestClient(create_app())


class TestLocalLlmSelftest:
    def test_ok_true_with_nonempty_reply_on_success(self, client, monkeypatch):
        from engine import local_llm

        monkeypatch.setattr(local_llm, "chat", lambda messages: "hello, I am the local model")
        resp = client.get("/api/diagnostics/local-llm-selftest")
        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is True
        assert body["reply"] == "hello, I am the local model"

    def test_ok_false_when_local_model_unavailable(self, client, monkeypatch):
        from engine import local_llm

        def _boom(messages):
            raise RuntimeError("local model unavailable")

        monkeypatch.setattr(local_llm, "chat", _boom)
        resp = client.get("/api/diagnostics/local-llm-selftest")
        # Still 200 — smoke_test.py distinguishes success via the "ok" field,
        # not the HTTP status, since a diagnostics route failing shouldn't
        # itself look like a server error.
        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is False
        assert body["reply"] == ""


class TestPdfSelftest:
    """007-T020: a REAL fpdf2 render with the bundled fonts — the smoke
    test asserts this in the frozen build so dropped font data files fail
    loudly (the tls_client lesson, third application)."""

    def test_renders_real_pdf(self, client):
        resp = client.get("/api/diagnostics/pdf-selftest")
        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is True
        assert body["bytes"] > 1000  # a real document, not a stub

    def test_ok_false_on_render_failure(self, client, monkeypatch):
        from engine import resume_pdf

        def _boom(*args, **kwargs):
            raise RuntimeError("font missing")

        monkeypatch.setattr(resume_pdf, "render_resume", _boom)
        resp = client.get("/api/diagnostics/pdf-selftest")
        assert resp.status_code == 200
        assert resp.json()["ok"] is False


class TestChromiumLaunchSelftest:
    """005-T030: packaging/smoke_test.py needs a real Chromium-launch check
    (not just an import check) so a dropped Playwright driver fails loudly,
    the same reasoning as the local-llm-selftest route above."""

    def test_ok_true_when_chromium_launches(self, client, monkeypatch):
        from engine.autofill import browser_controller

        monkeypatch.setattr(browser_controller, "chromium_selftest", lambda: True)
        resp = client.get("/api/diagnostics/chromium-launch-selftest")
        assert resp.status_code == 200
        assert resp.json()["ok"] is True

    def test_ok_false_when_chromium_launch_fails(self, client, monkeypatch):
        from engine.autofill import browser_controller

        def _boom():
            raise RuntimeError("driver missing")

        monkeypatch.setattr(browser_controller, "chromium_selftest", _boom)
        resp = client.get("/api/diagnostics/chromium-launch-selftest")
        assert resp.status_code == 200
        assert resp.json()["ok"] is False
