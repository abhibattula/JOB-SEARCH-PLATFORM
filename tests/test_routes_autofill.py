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


class TestQueueRoutes:
    def test_queue_reports_error_instead_of_silently_failing(self, client, monkeypatch):
        """Regression: a real failure inside browser_controller.start_queue
        (e.g. Chromium launch failing) must surface as a clear error the
        frontend can show, not a bare 500 the button's fetch() call ignores."""
        from engine.autofill import browser_controller

        monkeypatch.setattr(
            browser_controller, "preflight",
            lambda: {"ok": True, "channel": "msedge", "error": None},
        )

        def _boom(job_ids):
            raise RuntimeError("Executable doesn't exist at .../chromium/headless_shell.exe")

        monkeypatch.setattr(browser_controller, "start_queue", _boom)
        job_id = seed_job()

        resp = client.post("/api/autofill/queue", json={"job_ids": [job_id]})

        assert resp.status_code == 200
        body = resp.json()
        assert body["started"] is False
        assert "error" in body and body["error"]

    def test_queue_starts_and_returns_current_job(self, client, monkeypatch):
        from engine.autofill import browser_controller

        monkeypatch.setattr(
            browser_controller, "preflight",
            lambda: {"ok": True, "channel": "msedge", "error": None},
        )
        monkeypatch.setattr(browser_controller, "_open_job", lambda job_id: None)
        job_id = seed_job()

        resp = client.post("/api/autofill/queue", json={"job_ids": [job_id]})

        assert resp.status_code == 200
        body = resp.json()
        assert body["started"] is True
        assert body["current_job_id"] == job_id

    def test_next_advances_queue(self, client, monkeypatch):
        from engine.autofill import browser_controller

        monkeypatch.setattr(
            browser_controller, "preflight",
            lambda: {"ok": True, "channel": "msedge", "error": None},
        )
        monkeypatch.setattr(browser_controller, "_open_job", lambda job_id: None)
        j1, j2 = seed_job("https://x.example/1"), seed_job("https://x.example/2")
        client.post("/api/autofill/queue", json={"job_ids": [j1, j2]})

        resp = client.post("/api/autofill/next")

        assert resp.status_code == 200
        assert resp.json()["current_job_id"] == j2

    def test_next_reports_finished_when_queue_exhausted(self, client, monkeypatch):
        from engine.autofill import browser_controller

        monkeypatch.setattr(
            browser_controller, "preflight",
            lambda: {"ok": True, "channel": "msedge", "error": None},
        )
        monkeypatch.setattr(browser_controller, "_open_job", lambda job_id: None)
        j1 = seed_job()
        client.post("/api/autofill/queue", json={"job_ids": [j1]})

        resp = client.post("/api/autofill/next")

        assert resp.status_code == 200
        body = resp.json()
        assert body["current_job_id"] is None
        assert body["finished"] is True

    def test_stop_ends_queue(self, client, monkeypatch):
        from engine.autofill import browser_controller

        monkeypatch.setattr(
            browser_controller, "preflight",
            lambda: {"ok": True, "channel": "msedge", "error": None},
        )
        monkeypatch.setattr(browser_controller, "_open_job", lambda job_id: None)
        j1 = seed_job()
        client.post("/api/autofill/queue", json={"job_ids": [j1]})

        resp = client.post("/api/autofill/stop")

        assert resp.status_code == 200
        assert resp.json()["stopped"] is True

    def test_status_reflects_current_state(self, client, monkeypatch):
        from engine.autofill import browser_controller

        monkeypatch.setattr(
            browser_controller, "preflight",
            lambda: {"ok": True, "channel": "msedge", "error": None},
        )
        monkeypatch.setattr(browser_controller, "_open_job", lambda job_id: None)
        j1 = seed_job()
        client.post("/api/autofill/queue", json={"job_ids": [j1]})

        resp = client.get("/api/autofill/status")

        assert resp.status_code == 200
        body = resp.json()
        assert "chromium_installed" not in body
        assert body["queue_active"] is True
        assert body["current_job_id"] == j1


class TestDepthRoutes:
    """007-T027: extended status payload + rescan + resume-queue routes."""

    def _start_queue(self, client, monkeypatch, job_ids):
        from engine.autofill import browser_controller

        monkeypatch.setattr(
            browser_controller, "preflight",
            lambda: {"ok": True, "channel": "msedge", "error": None},
        )
        monkeypatch.setattr(browser_controller, "_open_job", lambda jid: None)
        resp = client.post("/api/autofill/queue", json={"job_ids": job_ids})
        assert resp.json()["started"] is True

    def test_status_includes_queue_progress_and_current_title(self, client, monkeypatch):
        j1 = seed_job("https://x.example/1")
        j2 = seed_job("https://x.example/2")
        self._start_queue(client, monkeypatch, [j1, j2])

        body = client.get("/api/autofill/status").json()

        assert body["progress"] == {"done": 0, "total": 2}
        states = {e["job_id"]: e["state"] for e in body["queue"]}
        assert states[j1] == "current" and states[j2] == "pending"
        current_entry = next(e for e in body["queue"] if e["state"] == "current")
        assert current_entry["title"] == "SWE"
        assert current_entry["company"] == "TestCo"
        assert body["fill_report"] == []
        assert body["interrupted"] is False
        assert body["summary"] is None

    def test_status_reports_summary_after_queue_ends(self, client, monkeypatch):
        j1 = seed_job("https://x.example/1")
        self._start_queue(client, monkeypatch, [j1])
        client.post("/api/autofill/next")  # past the end

        body = client.get("/api/autofill/status").json()

        assert body["summary"] is not None
        assert body["summary"]["per_job"][0]["job_id"] == j1

    def test_rescan_route_and_409_without_session(self, client, monkeypatch):
        from engine.autofill import browser_controller

        assert client.post("/api/autofill/rescan").status_code == 409

        j1 = seed_job("https://x.example/1")
        self._start_queue(client, monkeypatch, [j1])
        monkeypatch.setattr(
            browser_controller, "rescan", lambda: {"rescanned": True, "filled": 3}
        )
        body = client.post("/api/autofill/rescan").json()
        assert body == {"rescanned": True, "filled": 3}

    def test_resume_queue_route_and_409_without_interruption(self, client, monkeypatch):
        from engine.autofill import browser_controller

        assert client.post("/api/autofill/resume-queue").status_code == 409

        j1 = seed_job("https://x.example/1")
        self._start_queue(client, monkeypatch, [j1])
        browser_controller._mark_interrupted()
        body = client.post("/api/autofill/resume-queue").json()
        assert body["resumed"] is True


class TestConfirmAnswerRoute:
    """005-T034: the only write path into answer_bank (FR-011)."""

    def test_confirm_saves_to_answer_bank(self, client):
        from engine.autofill import answer_bank

        resp = client.post(
            "/api/autofill/answers/confirm",
            json={"question_raw": "How did you hear about us?",
                  "answer": "LinkedIn", "category": "how_heard"},
        )
        assert resp.status_code == 200
        assert resp.json()["saved"] is True
        assert answer_bank.lookup("How did you hear about us?")["answer"] == "LinkedIn"

    def test_confirm_records_per_application_snapshot_for_current_job(self, client, monkeypatch):
        from engine import db
        from engine.autofill import browser_controller

        monkeypatch.setattr(
            browser_controller, "preflight",
            lambda: {"ok": True, "channel": "msedge", "error": None},
        )
        monkeypatch.setattr(browser_controller, "_open_job", lambda job_id: None)
        job_id = seed_job()
        client.post("/api/autofill/queue", json={"job_ids": [job_id]})

        client.post(
            "/api/autofill/answers/confirm",
            json={"question_raw": "How did you hear about us?",
                  "answer": "LinkedIn", "category": "how_heard"},
        )

        with db._conn() as conn:
            row = conn.execute(
                "SELECT * FROM application_answers WHERE job_id = ?", (job_id,)
            ).fetchone()
        assert row is not None
        assert row["answer_used"] == "LinkedIn"

    def test_confirm_without_active_queue_still_saves_to_bank(self, client):
        """Confirming from the Profile-driven answer bank management UI
        (not just mid-queue) must still work — no active job required."""
        from engine.autofill import answer_bank

        resp = client.post(
            "/api/autofill/answers/confirm",
            json={"question_raw": "Years of Python experience?",
                  "answer": "3", "category": "years_experience"},
        )
        assert resp.status_code == 200
        assert answer_bank.lookup("Years of Python experience?") is not None


class TestAnswerBankManagement:
    """006-B: Profile page manages the answer bank directly."""

    def test_list_returns_saved_entries(self, client):
        client.post(
            "/api/autofill/answers/confirm",
            json={"question_raw": "How did you hear about us?",
                  "answer": "LinkedIn", "category": "how_heard"},
        )
        resp = client.get("/api/autofill/answers")
        assert resp.status_code == 200
        entries = resp.json()["entries"]
        assert len(entries) == 1
        assert entries[0]["question_raw"] == "How did you hear about us?"

    def test_delete_removes_entry(self, client):
        client.post(
            "/api/autofill/answers/confirm",
            json={"question_raw": "Q?", "answer": "A", "category": "how_heard"},
        )
        bank_id = client.get("/api/autofill/answers").json()["entries"][0]["id"]

        resp = client.delete(f"/api/autofill/answers/{bank_id}")

        assert resp.status_code == 200
        assert client.get("/api/autofill/answers").json()["entries"] == []


class TestPage:
    def test_autofill_page_serves(self, client):
        resp = client.get("/autofill")
        assert resp.status_code == 200

    def test_status_partial_serves_with_no_active_queue(self, client):
        resp = client.get("/partials/autofill/status")
        assert resp.status_code == 200

    def test_status_partial_renders_pending_confirmation(self, client, monkeypatch):
        """005-T035: the confirm-before-use UI must render without error
        when a pending drafted answer is present."""
        from engine.autofill import browser_controller

        monkeypatch.setattr(
            browser_controller, "current_job",
            lambda: {
                "job_id": 1, "remaining": 0, "fell_back": False,
                "pending": {
                    "question_raw": "How did you hear about us?",
                    "category": "how_heard",
                    "drafted_answer": "Found it on LinkedIn",
                },
            },
        )
        resp = client.get("/partials/autofill/status")
        assert resp.status_code == 200
        assert "How did you hear about us?" in resp.text
        assert "unreviewed" in resp.text

    def test_status_partial_renders_sensitive_pending_badge(self, client, monkeypatch):
        from engine.autofill import browser_controller

        monkeypatch.setattr(
            browser_controller, "current_job",
            lambda: {
                "job_id": 1, "remaining": 0, "fell_back": False,
                "pending": {
                    "question_raw": "Do you require visa sponsorship?",
                    "category": "sponsorship_requirement",
                    "drafted_answer": "",
                },
            },
        )
        resp = client.get("/partials/autofill/status")
        assert resp.status_code == 200
        assert "sensitive" in resp.text


class Test008BrowserRoutes:
    """008 US1 (T010): preflight-gated queue, retired setup route, and the
    browser/outcomes status payload."""

    def test_setup_route_is_gone(self, client):
        resp = client.post("/api/autofill/setup")
        assert resp.status_code == 410

    def test_preflight_route_reports_result(self, client, monkeypatch):
        from engine.autofill import browser_controller

        monkeypatch.setattr(
            browser_controller, "preflight",
            lambda: {"ok": True, "channel": "msedge", "error": None},
        )
        resp = client.post("/api/autofill/preflight")
        assert resp.status_code == 200
        assert resp.json() == {"ok": True, "channel": "msedge", "error": None}

    def test_queue_refuses_to_start_when_preflight_fails(self, client, monkeypatch):
        from engine.autofill import browser_controller

        monkeypatch.setattr(
            browser_controller, "preflight",
            lambda: {"ok": False, "channel": None,
                     "error": "msedge: not installed; chrome: not installed"},
        )

        def never(job_ids):
            raise AssertionError("start_queue must not run after failed preflight")

        monkeypatch.setattr(browser_controller, "start_queue", never)
        job_id = seed_job("https://x.example/pf1")
        resp = client.post("/api/autofill/queue", json={"job_ids": [job_id]})
        assert resp.status_code == 409
        assert "not installed" in resp.json()["detail"]

    def test_queue_starts_after_preflight_ok(self, client, monkeypatch):
        from engine.autofill import browser_controller

        monkeypatch.setattr(
            browser_controller, "preflight",
            lambda: {"ok": True, "channel": "msedge", "error": None},
        )
        monkeypatch.setattr(browser_controller, "_open_job", lambda job_id: None)
        job_id = seed_job("https://x.example/pf2")
        resp = client.post("/api/autofill/queue", json={"job_ids": [job_id]})
        assert resp.status_code == 200
        assert resp.json()["started"] is True

    def test_status_exposes_browser_and_outcomes_not_chromium_flag(
        self, client, monkeypatch
    ):
        from engine.autofill import browser_controller

        monkeypatch.setattr(
            browser_controller, "preflight",
            lambda: {"ok": True, "channel": "msedge", "error": None},
        )
        monkeypatch.setattr(browser_controller, "_open_job", lambda job_id: None)
        job_id = seed_job("https://x.example/pf3")
        client.post("/api/autofill/queue", json={"job_ids": [job_id]})
        with browser_controller._lock:
            browser_controller._state.outcomes[job_id] = {
                "reason": "nav_failed", "detail": "timeout"}
        body = client.get("/api/autofill/status").json()
        assert "chromium_installed" not in body
        assert body["browser"]["ok"] is True
        assert body["outcomes"] == [
            {"job_id": job_id, "reason": "nav_failed", "detail": "timeout"}
        ]
