"""005-T027/T028: web/routes_autofill.py — thin routes per contracts/http-api.md.
No automation logic lives here; every route is a thin call into
engine/autofill/browser_controller.py or browser_setup.py."""
import pytest
from fastapi.testclient import TestClient

from engine import db


@pytest.fixture()
def client(tmp_db, monkeypatch):
    monkeypatch.setenv("REFRESH_SYNC", "1")
    from engine import pipeline

    monkeypatch.setattr(pipeline, "_source_names", lambda: [])
    monkeypatch.setattr(pipeline, "load_companies", lambda: [])
    from web.main import create_app

    return TestClient(create_app())


def seed_job(url="https://x.example/1"):
    db.upsert_job(
        {"title": "SWE", "company": "TestCo", "url": url,
         "source": "greenhouse", "description": "desc"}
    )
    jobs, _ = db.query_jobs(window=None, statuses=None, entry_level=None)
    return next(j for j in jobs if j["url"] == url)["id"]


class TestSetupRoute:
    def test_setup_starts_when_not_installed(self, client, monkeypatch):
        from engine.autofill import browser_setup

        monkeypatch.setattr(browser_setup, "is_installed", lambda: False)
        started = {}
        monkeypatch.setattr(
            browser_setup, "start_install",
            lambda background=True: started.setdefault("called", background) or True,
        )
        resp = client.post("/api/autofill/setup")
        assert resp.status_code == 200
        assert resp.json()["started"] is True

    def test_setup_reports_already_installed(self, client, monkeypatch):
        from engine.autofill import browser_setup

        monkeypatch.setattr(browser_setup, "is_installed", lambda: True)
        resp = client.post("/api/autofill/setup")
        assert resp.status_code == 200
        body = resp.json()
        assert body["started"] is False
        assert body["reason"] == "already_installed"


class TestQueueRoutes:
    def test_queue_requires_chromium_installed(self, client, monkeypatch):
        from engine.autofill import browser_setup

        monkeypatch.setattr(browser_setup, "is_installed", lambda: False)
        job_id = seed_job()
        resp = client.post("/api/autofill/queue", json={"job_ids": [job_id]})
        assert resp.status_code == 409

    def test_queue_starts_and_returns_current_job(self, client, monkeypatch):
        from engine.autofill import browser_controller, browser_setup

        monkeypatch.setattr(browser_setup, "is_installed", lambda: True)
        monkeypatch.setattr(browser_controller, "_open_job", lambda job_id: None)
        job_id = seed_job()

        resp = client.post("/api/autofill/queue", json={"job_ids": [job_id]})

        assert resp.status_code == 200
        body = resp.json()
        assert body["started"] is True
        assert body["current_job_id"] == job_id

    def test_next_advances_queue(self, client, monkeypatch):
        from engine.autofill import browser_controller, browser_setup

        monkeypatch.setattr(browser_setup, "is_installed", lambda: True)
        monkeypatch.setattr(browser_controller, "_open_job", lambda job_id: None)
        j1, j2 = seed_job("https://x.example/1"), seed_job("https://x.example/2")
        client.post("/api/autofill/queue", json={"job_ids": [j1, j2]})

        resp = client.post("/api/autofill/next")

        assert resp.status_code == 200
        assert resp.json()["current_job_id"] == j2

    def test_next_reports_finished_when_queue_exhausted(self, client, monkeypatch):
        from engine.autofill import browser_controller, browser_setup

        monkeypatch.setattr(browser_setup, "is_installed", lambda: True)
        monkeypatch.setattr(browser_controller, "_open_job", lambda job_id: None)
        j1 = seed_job()
        client.post("/api/autofill/queue", json={"job_ids": [j1]})

        resp = client.post("/api/autofill/next")

        assert resp.status_code == 200
        body = resp.json()
        assert body["current_job_id"] is None
        assert body["finished"] is True

    def test_stop_ends_queue(self, client, monkeypatch):
        from engine.autofill import browser_controller, browser_setup

        monkeypatch.setattr(browser_setup, "is_installed", lambda: True)
        monkeypatch.setattr(browser_controller, "_open_job", lambda job_id: None)
        j1 = seed_job()
        client.post("/api/autofill/queue", json={"job_ids": [j1]})

        resp = client.post("/api/autofill/stop")

        assert resp.status_code == 200
        assert resp.json()["stopped"] is True

    def test_status_reflects_current_state(self, client, monkeypatch):
        from engine.autofill import browser_controller, browser_setup

        monkeypatch.setattr(browser_setup, "is_installed", lambda: True)
        monkeypatch.setattr(browser_controller, "_open_job", lambda job_id: None)
        j1 = seed_job()
        client.post("/api/autofill/queue", json={"job_ids": [j1]})

        resp = client.get("/api/autofill/status")

        assert resp.status_code == 200
        body = resp.json()
        assert body["chromium_installed"] is True
        assert body["queue_active"] is True
        assert body["current_job_id"] == j1


class TestPage:
    def test_autofill_page_serves(self, client):
        resp = client.get("/autofill")
        assert resp.status_code == 200
