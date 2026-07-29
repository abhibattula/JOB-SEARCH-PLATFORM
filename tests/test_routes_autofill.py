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
        {"title": f"SWE {url.rsplit('/', 1)[-1]}", "company": "TestCo", "url": url,
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
        monkeypatch.setattr(browser_controller, "_dispatch", lambda name, payload=None, wait=None: None)
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
        monkeypatch.setattr(browser_controller, "_dispatch", lambda name, payload=None, wait=None: None)
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
        monkeypatch.setattr(browser_controller, "_dispatch", lambda name, payload=None, wait=None: None)
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
        monkeypatch.setattr(browser_controller, "_dispatch", lambda name, payload=None, wait=None: None)
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
        monkeypatch.setattr(browser_controller, "_dispatch", lambda name, payload=None, wait=None: None)
        j1 = seed_job()
        client.post("/api/autofill/queue", json={"job_ids": [j1]})

        resp = client.get("/api/autofill/status")

        assert resp.status_code == 200
        body = resp.json()
        assert "chromium_installed" not in body
        assert body["queue_active"] is True
        assert body["current_job_id"] == j1
        # 010: status carries the active backend + companion state
        assert body["backend"] in ("extension", "playwright")
        assert "connected" in body["extension"]


class TestDepthRoutes:
    """007-T027: extended status payload + rescan + resume-queue routes."""

    def _start_queue(self, client, monkeypatch, job_ids):
        from engine.autofill import browser_controller

        monkeypatch.setattr(
            browser_controller, "preflight",
            lambda: {"ok": True, "channel": "msedge", "error": None},
        )
        monkeypatch.setattr(browser_controller, "_dispatch", lambda name, payload=None, wait=None: None)
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
        assert current_entry["title"] == "SWE 1"
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
            browser_controller, "rescan", lambda: {"forced": True}
        )
        body = client.post("/api/autofill/rescan").json()
        assert body == {"forced": True}

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
        monkeypatch.setattr(browser_controller, "_dispatch", lambda name, payload=None, wait=None: None)
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

    def test_status_partial_renders_activity_log(self, client, monkeypatch):
        """016 (FR-019): the passive activity log renders drafting/drafted/
        needs-you entries (the 005 confirm-before-use gate is gone)."""
        from engine.autofill import browser_controller

        monkeypatch.setattr(
            browser_controller, "current_job",
            lambda: {
                "job_id": 1, "remaining": 0, "fell_back": False,
                "activity": [
                    {"question": "How did you hear about us?",
                     "state": "drafted",
                     "answer_preview": "Found it on LinkedIn",
                     "reason": None},
                    {"question": "Tell us about a project",
                     "state": "drafting", "answer_preview": "",
                     "reason": None},
                    {"question": "What is your ethnicity?",
                     "state": "needs_you", "answer_preview": "",
                     "reason": "sensitive"},
                ],
            },
        )
        resp = client.get("/partials/autofill/status")
        assert resp.status_code == 200
        assert "How did you hear about us?" in resp.text
        assert "Found it on LinkedIn" in resp.text
        assert "drafting" in resp.text
        assert "needs you" in resp.text


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
        monkeypatch.setattr(browser_controller, "_dispatch", lambda name, payload=None, wait=None: None)
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
        monkeypatch.setattr(browser_controller, "_dispatch", lambda name, payload=None, wait=None: None)
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


class Test009Practice:
    """009 US2 (T013): the bundled practice application — the ten-second
    on-machine proof, queued through the normal engine."""

    def test_practice_pages_render(self, client):
        page = client.get("/practice/apply")
        assert page.status_code == 200
        text = page.text
        assert 'name="first_name"' in text
        assert 'name="email"' in text
        assert 'name="phone"' in text
        assert 'type="file"' in text
        assert "<select" in text  # work-authorization dropdown
        assert "setTimeout" in text  # the delayed-render section
        assert "/practice/frame" in text  # the embedded-frame section
        frame = client.get("/practice/frame")
        assert frame.status_code == 200
        assert 'name="urls[LinkedIn]"' in frame.text

    def test_practice_route_starts_a_practice_queue(self, client, monkeypatch):
        from engine.autofill import browser_controller

        monkeypatch.setattr(
            browser_controller, "preflight",
            lambda: {"ok": True, "channel": "msedge", "error": None},
        )
        started = {}
        monkeypatch.setattr(
            browser_controller, "start_practice",
            lambda url: started.setdefault("url", url) or {"job_id": -1},
        )
        resp = client.post("/api/autofill/practice")
        assert resp.status_code == 200
        assert resp.json()["started"] is True
        assert started["url"].endswith("/practice/apply")

    def test_practice_refused_while_queue_active(self, client, monkeypatch):
        from engine.autofill import browser_controller

        monkeypatch.setattr(
            browser_controller, "preflight",
            lambda: {"ok": True, "channel": "msedge", "error": None},
        )
        monkeypatch.setattr(browser_controller, "start_practice", lambda url: None)
        assert client.post("/api/autofill/practice").status_code == 409

    def test_autofill_page_offers_test_button(self, client):
        resp = client.get("/autofill")
        assert "Test Apply Assist" in resp.text


class Test010Drafts:
    """010 US2: the AI-draft review endpoints."""

    def test_list_drafts_empty_without_session(self, client):
        resp = client.get("/api/autofill/drafts")
        assert resp.status_code == 200
        assert resp.json()["drafts"] == []

    def test_confirm_draft_saves_answer(self, client):
        from engine.autofill import answer_bank, drafts

        did = drafts.record(None, "Why do you want to work here?",
                            "Draft about my UVM work.", "local")
        resp = client.post(f"/api/autofill/drafts/{did}",
                           json={"action": "confirm", "text": "Final edited answer."})
        assert resp.status_code == 200
        assert resp.json()["status"] == "confirmed"
        saved = answer_bank.lookup("Why do you want to work here?")
        assert saved["answer"] == "Final edited answer."
        assert saved["source"] == "confirmed"

    def test_discard_draft(self, client):
        from engine.autofill import drafts

        did = drafts.record(None, "Q?", "x", "local")
        resp = client.post(f"/api/autofill/drafts/{did}", json={"action": "discard"})
        assert resp.status_code == 200
        assert drafts.get(did)["status"] == "discarded"

    def test_confirm_missing_draft_404(self, client):
        resp = client.post("/api/autofill/drafts/9999", json={"action": "confirm"})
        assert resp.status_code == 404

    def test_bad_action_400(self, client):
        from engine.autofill import drafts

        did = drafts.record(None, "Q?", "x", "local")
        resp = client.post(f"/api/autofill/drafts/{did}", json={"action": "nope"})
        assert resp.status_code == 400


class Test010ApplyAssistScreen:
    def test_page_has_connection_card_and_companion_link(self, client):
        resp = client.get("/autofill")
        assert resp.status_code == 200
        assert 'id="companion-card"' in resp.text
        assert 'href="/companion"' in resp.text
        assert "assistant window" in resp.text


class Test011FillCoverage:
    def test_status_partial_shows_fill_coverage(self, client, monkeypatch):
        from engine.autofill import browser_controller as bc
        monkeypatch.setattr(bc, "_dispatch", lambda *a, **k: None)
        # seed a fill report with a filled + a needs_manual entry
        with bc._lock:
            bc._state.running = True
            bc._state.job_ids = [1]
            bc._state.index = 0
            bc._state.fill_reports = {1: [
                {"label": "First name", "tag": "first_name",
                 "value_preview": "Abhinav", "outcome": "filled", "ai_draft": False},
                {"label": "Work auth", "tag": "work_authorization",
                 "value_preview": "", "outcome": "needs_manual", "ai_draft": False},
            ]}
        resp = client.get("/partials/autofill/status")
        assert resp.status_code == 200
        assert "fill-coverage" in resp.text
        assert "need" in resp.text  # "1 need you"
        bc.stop_queue()


class TestBackendDisclosure015:
    """015 (D2/FR-012): the queue-start response names the fill path so the
    UI can show the loud notice from the very first render."""

    def test_queue_response_names_playwright_backend(self, client, monkeypatch):
        from engine.autofill import browser_controller

        monkeypatch.setattr(
            browser_controller, "preflight",
            lambda: {"ok": True, "channel": "msedge", "error": None},
        )
        monkeypatch.setattr(browser_controller, "_dispatch",
                            lambda name, payload=None, wait=None: None)
        job_id = seed_job()
        body = client.post("/api/autofill/queue",
                           json={"job_ids": [job_id]}).json()
        assert body["started"] is True
        assert body["backend"] == "playwright"  # no live companion

    def test_queue_response_names_extension_backend(self, client, monkeypatch):
        from engine.autofill import browser_controller, ext_backend

        monkeypatch.setattr(
            browser_controller, "preflight",
            lambda: {"ok": True, "channel": "msedge", "error": None},
        )
        sent = []
        ext_backend.register(sent.append, lambda code: None, "1.5.0",
                             browser="chrome")
        job_id = seed_job()
        body = client.post("/api/autofill/queue",
                           json={"job_ids": [job_id]}).json()
        assert body["started"] is True
        assert body["backend"] == "extension"


class TestConfirmAnswerSentinel015:
    """015 (FR-020): confirming during practice (-1) / ad-hoc (-2) sessions
    must succeed — the reusable answer saves, NO per-application snapshot row
    is written (sentinel ids have no jobs row; this 500'd with a FOREIGN KEY
    error on the evidence machine)."""

    def _confirm(self, client):
        return client.post("/api/autofill/answers/confirm", json={
            "question_raw": "Why do you want to work here?",
            "answer": "Because the mission fits my skills.",
            "category": "free_text_unknown",
        })

    def _snapshot_count(self):
        with db._conn() as conn:
            return conn.execute(
                "SELECT COUNT(*) FROM application_answers").fetchone()[0]

    def test_practice_session_confirm_succeeds_without_snapshot(
            self, client, monkeypatch):
        from engine.autofill import answer_bank, browser_controller

        monkeypatch.setattr(browser_controller, "current_job",
                            lambda: {"job_id": -1, "remaining": 0,
                                     "fell_back": False, "pending": None})
        resp = self._confirm(client)
        assert resp.status_code == 200
        assert resp.json() == {"saved": True}
        assert len(answer_bank.list_all()) == 1  # reusable answer saved
        assert self._snapshot_count() == 0       # no snapshot for sentinels

    def test_adhoc_session_confirm_succeeds(self, client, monkeypatch):
        from engine.autofill import browser_controller

        monkeypatch.setattr(browser_controller, "current_job",
                            lambda: {"job_id": -2, "remaining": 0,
                                     "fell_back": False, "activity": []})
        assert self._confirm(client).status_code == 200
        assert self._snapshot_count() == 0

    def test_real_job_still_snapshots(self, client, monkeypatch):
        from engine.autofill import browser_controller

        job_id = seed_job()
        monkeypatch.setattr(browser_controller, "current_job",
                            lambda: {"job_id": job_id, "remaining": 0,
                                     "fell_back": False, "activity": []})
        assert self._confirm(client).status_code == 200
        assert self._snapshot_count() == 1


class TestFillFirstRoutes016:
    """016 (T006, FR-009/FR-019): a live companion skips the Playwright
    preflight at queue start, and the confirm endpoints are bank-curation
    only — no resolve/fill side effects exist anymore."""

    def test_queue_skips_preflight_with_live_companion(self, client, monkeypatch):
        from engine.autofill import browser_controller, ext_backend

        job_id = seed_job()
        monkeypatch.setattr(ext_backend, "is_live", lambda *a, **k: True)

        def boom():
            raise AssertionError("preflight must not run with a live companion")

        monkeypatch.setattr(browser_controller, "preflight", boom)
        monkeypatch.setattr(browser_controller, "start_queue",
                            lambda ids: {"job_id": ids[0], "remaining": 0,
                                         "fell_back": False, "activity": []})
        response = client.post("/api/autofill/queue", json={"job_ids": [job_id]})
        assert response.status_code == 200
        assert response.json()["started"] is True

    def test_queue_still_preflights_without_companion(self, client, monkeypatch):
        from engine.autofill import browser_controller, ext_backend

        job_id = seed_job("https://x.example/2")
        monkeypatch.setattr(ext_backend, "is_live", lambda *a, **k: False)
        monkeypatch.setattr(browser_controller, "preflight",
                            lambda: {"ok": False, "channel": None,
                                     "error": "no browser"})
        response = client.post("/api/autofill/queue", json={"job_ids": [job_id]})
        assert response.status_code == 409

    def test_confirm_answer_saves_bank_only(self, client):
        from engine.autofill import answer_bank, browser_controller

        assert not hasattr(browser_controller, "resolve_pending")
        response = client.post("/api/autofill/answers/confirm", json={
            "question_raw": "What is your notice period?",
            "answer": "Two weeks", "category": "notice_period"})
        assert response.status_code == 200
        saved = answer_bank.lookup("What is your notice period?")
        assert saved is not None and saved["answer"] == "Two weeks"


class TestPurgeLearnedAnswers017:
    """017-T023 (FR-011, FR-046): the applicant can remove what the model
    invented, and only that.

    The drafter auto-saves accepted answers to the bank, so the 2026-07-28
    run's fabrications ("Yes, I have applied to Akuna in the past") would
    refill on every future application until they can be deleted. Answers the
    applicant wrote themselves must survive.
    """

    def _seed(self):
        from engine.autofill import answer_bank, drafts

        answer_bank.save_auto(question="Invented?", answer="Yes, in the past",
                              tag="free_text_unknown", origin="ai")
        answer_bank.save_with_provenance("Auto saved?", "Something",
                                         "auto_saved")
        answer_bank.save("My own answer?", "3.2", category="gpa")
        drafts.record(5, "Drafted?", "Some draft", tier="local")

    def test_counts_are_reported_before_deleting(self, client):
        self._seed()
        body = client.get("/api/autofill/answers/learned").json()
        assert body["answers"] == 2
        assert body["drafts"] == 1

    def test_purge_removes_only_model_written_rows(self, client):
        from engine.autofill import answer_bank, drafts

        self._seed()
        body = client.post("/api/autofill/answers/purge").json()
        assert body["removed_answers"] == 2
        assert body["removed_drafts"] == 1

        remaining = {row["question_raw"] for row in answer_bank.list_all()}
        assert remaining == {"My own answer?"}
        assert drafts.list_for_job(5) == []

    def test_purge_is_idempotent(self, client):
        self._seed()
        client.post("/api/autofill/answers/purge")
        body = client.post("/api/autofill/answers/purge").json()
        assert body == {"removed_answers": 0, "removed_drafts": 0}

    def test_an_answer_the_applicant_typed_is_never_removed(self, client):
        """FR-046: panel-captured answers are stored as the applicant's own
        precisely so a purge cannot destroy them."""
        from engine.autofill import answer_bank

        answer_bank.save("Do you live in New York or California?", "No",
                         category="residency_state")
        client.post("/api/autofill/answers/purge")
        assert answer_bank.lookup(
            "Do you live in New York or California?")["answer"] == "No"


class TestControlsAlwaysReachable017:
    """017-T025 (FR-009/FR-010): Stop must be reachable at any form size.

    On the 2026-07-28 run a 91-field application plus a 170-row review list
    pushed the controls so far down the page that the applicant could not
    scroll to Stop at all.
    """

    def _running_session(self, monkeypatch, drafts_count=0):
        from engine.autofill import browser_controller, drafts as drafts_mod

        monkeypatch.setattr(
            browser_controller, "current_job",
            lambda: {"job_id": 1, "remaining": 0, "fell_back": False,
                     "activity": []},
        )
        rows = [{"id": index, "question": f"Question {index}?",
                 "draft_text": f"Answer {index}", "status": "drafted"}
                for index in range(drafts_count)]
        monkeypatch.setattr(drafts_mod, "list_for_job", lambda job_id: rows)

    def test_controls_render_before_the_report_and_drafts(
            self, client, monkeypatch):
        self._running_session(monkeypatch, drafts_count=40)
        body = client.get("/partials/autofill/status").text

        controls = body.index('id="autofill-controls"')
        assert "Stop" in body
        assert controls < body.index('id="ai-drafts-review"'), \
            "the controls must come before the draft list, not after it"

    def test_the_draft_list_is_bounded(self, client, monkeypatch):
        self._running_session(monkeypatch, drafts_count=170)
        body = client.get("/partials/autofill/status").text

        assert body.count('class="ai-draft"') <= 20
        assert "Showing the 20 most recent" in body

    def test_a_short_list_renders_in_full_without_the_notice(
            self, client, monkeypatch):
        self._running_session(monkeypatch, drafts_count=3)
        body = client.get("/partials/autofill/status").text

        assert body.count('class="ai-draft"') == 3
        assert "Showing the 20 most recent" not in body

    def test_the_polled_region_does_not_move_the_viewport(self, client):
        """A swap that re-anchors the scroll makes a long page unusable."""
        body = client.get("/autofill").text
        assert 'hx-swap="innerHTML show:none"' in body


class TestApplyWithAssist017:
    """017-T068 (FR-040): start Apply Assist for one job, from that job.

    The only entry point used to be the Apply Assist page, which lists only
    jobs that are already saved AND passed the entry-level filter — so the
    job you were reading could not be filled without a detour.
    """

    def test_it_starts_a_single_job_session(self, client, monkeypatch):
        from engine.autofill import browser_controller

        started = {}

        def fake_start(job_ids):
            started["ids"] = job_ids
            return {"job_id": job_ids[0]}

        monkeypatch.setattr(browser_controller, "start_queue", fake_start)
        monkeypatch.setattr(browser_controller, "preflight",
                            lambda: {"ok": True, "channel": "chrome",
                                     "error": None})
        job_id = seed_job("https://x.example/apply-with-assist")

        resp = client.post(f"/api/autofill/apply/{job_id}")

        assert resp.status_code == 200
        assert resp.json()["started"] is True
        assert started["ids"] == [job_id]

    def test_it_saves_the_job_first(self, client, monkeypatch):
        from engine import db
        from engine.autofill import browser_controller

        monkeypatch.setattr(browser_controller, "start_queue",
                            lambda ids: {"job_id": ids[0]})
        monkeypatch.setattr(browser_controller, "preflight",
                            lambda: {"ok": True, "channel": "chrome",
                                     "error": None})
        job_id = seed_job("https://x.example/apply-saves")

        client.post(f"/api/autofill/apply/{job_id}")

        assert db.get_job(job_id)["status"] == "saved"

    def test_an_applied_job_is_not_reset_to_saved(self, client, monkeypatch):
        from engine import db
        from engine.autofill import browser_controller

        monkeypatch.setattr(browser_controller, "start_queue",
                            lambda ids: {"job_id": ids[0]})
        monkeypatch.setattr(browser_controller, "preflight",
                            lambda: {"ok": True, "channel": "chrome",
                                     "error": None})
        job_id = seed_job("https://x.example/apply-already-applied")
        db.set_status(job_id, "applied")

        client.post(f"/api/autofill/apply/{job_id}")

        assert db.get_job(job_id)["status"] == "applied"

    def test_an_unknown_job_is_404(self, client):
        assert client.post("/api/autofill/apply/999999").status_code == 404

    def test_the_job_page_offers_the_action(self, client):
        job_id = seed_job("https://x.example/apply-button")
        body = client.get(f"/jobs/{job_id}").text
        assert 'id="apply-with-assist"' in body
        assert f"/api/autofill/apply/{job_id}" in body
