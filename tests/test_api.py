"""T009: HTTP contract tests per contracts/http-api.md (US1 endpoints)."""
import pytest
from fastapi.testclient import TestClient

from engine import db


@pytest.fixture()
def client(tmp_db, monkeypatch):
    # Refresh runs synchronously (and fetches nothing) so tests are deterministic.
    monkeypatch.setenv("REFRESH_SYNC", "1")
    from engine import matcher, pipeline

    monkeypatch.setattr(pipeline, "_source_names", lambda: [])
    monkeypatch.setattr(pipeline, "load_companies", lambda: [])
    # 007: force the basic tier — a dev machine with the bundled model in
    # models/ would otherwise run REAL local-LLM extraction on every
    # unmocked resume upload (slow, nondeterministic). Tests that need
    # extraction mock engine.resume_extract.extract directly.
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.setattr(matcher.local_llm, "available", lambda: False)
    from web.main import create_app

    return TestClient(create_app())


def seed_job(**overrides):
    job = {
        "title": "Software Engineer, New Grad",
        "company": "Stripe",
        "url": "https://example.com/job/1",
        "source": "greenhouse",
        "location": "San Francisco, CA",
        "is_remote": False,
        "description": "desc",
        "posted_date": None,  # first_seen fallback keeps it in every window
    }
    job.update(overrides)
    db.upsert_job(job)
    jobs, _ = db.query_jobs(window=None, statuses=None, entry_level=None)
    seeded = next(j for j in jobs if j["url"] == job["url"])
    # mirror the pipeline's classification stage so seeded jobs pass the
    # entry-level default filter
    db.set_classification(seeded["id"], True, "UNKNOWN", None)
    return seeded


class TestPages:
    def test_index_serves_html(self, client):
        response = client.get("/")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]

    def test_feed_partial_serves_html(self, client):
        assert client.get("/partials/feed").status_code == 200

    def test_job_detail_page(self, client):
        job = seed_job()
        assert client.get(f"/jobs/{job['id']}").status_code == 200
        assert client.get("/jobs/99999").status_code == 404

    def test_profile_page_serves_empty(self, client):
        assert client.get("/profile").status_code == 200

    def test_profile_page_renders_answer_bank_entries(self, client):
        """006-B/C: the Common Questions + EEO disclosures section must
        render without error, including when an EEO answer is pre-filled."""
        from engine.autofill import answer_bank

        answer_bank.save("How did you hear about us?", "LinkedIn", category="how_heard")
        answer_bank.save("What is your gender?", "Prefer not to say", category="eeo_disclosure")

        resp = client.get("/profile")

        assert resp.status_code == 200
        assert "How did you hear about us?" in resp.text
        assert "Prefer not to say" in resp.text

    def test_feed_polling_is_gated_and_editors_preserved(self, client):
        """007-T010 (FR-024): the 5s feed poll must be conditional on
        pollingAllowed() so background refreshes never clobber an open
        notes/stage editor mid-edit."""
        resp = client.get("/")
        assert resp.status_code == 200
        assert "every 5s [pollingAllowed()]" in resp.text
        # base page loads the shared module that defines the gate
        assert "/static/app.js" in resp.text

    def test_nav_marks_current_page(self, client):
        """007-T009 (FR-022): grouped nav with aria-current active state."""
        resp = client.get("/profile")
        assert 'aria-current="page"' in resp.text
        assert resp.text.count('aria-current="page"') == 1

    def test_profile_page_renders_resume_builder(self, client):
        """007-T015: the Resume builder section renders populated
        sections, and empty editable state when none exist."""
        from engine import db

        empty = client.get("/profile")
        assert empty.status_code == 200
        assert "Resume builder" in empty.text

        db.save_profile(resume_sections={
            "experience": [{"title": "Firmware Intern", "organization": "Acme",
                            "start": "2025-05", "end": "2025-08",
                            "bullets": ["Wrote STM32 drivers"]}],
            "education": [], "projects": [], "skills": ["python"],
        })
        populated = client.get("/profile")
        assert "Firmware Intern" in populated.text
        assert "Wrote STM32 drivers" in populated.text

    def test_profile_page_shows_reextract_prompt_on_conflict(self, client):
        """007-T015 (FR-016 clarification): after an upload that skipped
        extraction because edits exist, the page asks keep vs re-extract."""
        resp = client.get("/profile?extraction_conflict=1")
        assert resp.status_code == 200
        assert "Re-extract" in resp.text
        assert "keep" in resp.text.lower()

    def test_profile_page_serves_with_sponsorship_fields_set(self, client):
        """005-T036: profile.html must render the Apply Assist fields
        section without error for a populated profile."""
        from engine import db

        db.save_profile(
            resume_text="resume", resume_filename="r.pdf",
            authorized_without_sponsorship="no", visa_status="OPT",
        )
        resp = client.get("/profile")
        assert resp.status_code == 200
        assert "OPT" in resp.text


class TestJobsApi:
    def test_list_shape_and_filters(self, client):
        seed_job(url="https://example.com/1", title="Job One")
        seed_job(url="https://example.com/2", title="Job Two", location="Austin, TX")
        response = client.get("/api/jobs")
        assert response.status_code == 200
        payload = response.json()
        assert payload["total"] == 2
        job = payload["jobs"][0]
        for key in ("id", "title", "company", "location", "url", "source",
                    "sponsorship", "match_score", "status", "is_new"):
            assert key in job
        narrowed = client.get("/api/jobs", params={"location": "Austin"}).json()
        assert narrowed["total"] == 1

    def test_excluded_hidden_by_default_and_ineligible_view(self, client):
        eligible = seed_job(url="https://example.com/ok", title="Eligible Job")
        excluded = seed_job(url="https://example.com/no", title="Clearance Job")
        db.set_classification(excluded["id"], True, "EXCLUDED", {"phrase": "itar"})

        default = client.get("/api/jobs").json()
        assert default["total"] == 1
        assert default["jobs"][0]["id"] == eligible["id"]

        audit = client.get("/api/jobs", params={"ineligible": 1}).json()
        assert audit["total"] == 1
        assert audit["jobs"][0]["sponsorship"] == "EXCLUDED"

    def test_min_score_filter(self, client):
        high = seed_job(url="https://example.com/hi", title="High Match")
        seed_job(url="https://example.com/lo", title="Low Match")
        seed_job(url="https://example.com/un", title="Unscored")
        db.set_match(high["id"], 88.0, "{}")
        jobs, _ = db.query_jobs(window=None, statuses=None)
        low = next(j for j in jobs if j["url"].endswith("/lo"))
        db.set_match(low["id"], 40.0, "{}")

        filtered = client.get("/api/jobs", params={"min_score": 70}).json()
        assert filtered["total"] == 1
        assert filtered["jobs"][0]["title"] == "High Match"
        assert client.get("/api/jobs").json()["total"] == 3  # no threshold

    def test_job_detail_and_404(self, client):
        job = seed_job()
        detail = client.get(f"/api/jobs/{job['id']}")
        assert detail.status_code == 200
        assert detail.json()["description"] == "desc"
        assert client.get("/api/jobs/99999").status_code == 404

    def test_status_roundtrip_and_errors(self, client):
        job = seed_job()
        ok = client.post(f"/api/jobs/{job['id']}/status", json={"status": "applied"})
        assert ok.status_code == 200
        assert ok.json()["status"] == "applied"
        assert client.get("/api/jobs").json()["total"] == 0  # applied leaves feed
        assert (
            client.post(f"/api/jobs/{job['id']}/status", json={"status": "bogus"})
            .status_code == 400
        )
        assert (
            client.post("/api/jobs/99999/status", json={"status": "saved"})
            .status_code == 404
        )


class TestProfileApi:
    def _pdf(self):
        import fitz

        doc = fitz.open()
        page = doc.new_page()
        page.insert_text(
            (72, 72),
            "ABHINAV B - Computer Engineering 2026. Skills: Python, Verilog, FPGA.",
        )
        return doc.tobytes()

    def test_get_empty_profile(self, client):
        response = client.get("/api/profile")
        assert response.status_code == 200
        assert response.json()["resume_filename"] is None

    def test_upload_resume_and_locations(self, client):
        response = client.post(
            "/api/profile",
            files={"resume": ("resume.pdf", self._pdf(), "application/pdf")},
            data={"target_locations": "CA, TX, Remote"},
        )
        assert response.status_code == 200
        payload = client.get("/api/profile").json()
        assert payload["resume_filename"] == "resume.pdf"
        assert payload["target_locations"] == ["CA", "TX", "Remote"]
        assert isinstance(payload["skills"], list)  # empty without an LLM key

    def test_update_locations_keeps_resume(self, client):
        client.post(
            "/api/profile",
            files={"resume": ("resume.pdf", self._pdf(), "application/pdf")},
        )
        client.post("/api/profile", data={"target_locations": "NY"})
        payload = client.get("/api/profile").json()
        assert payload["resume_filename"] == "resume.pdf"
        assert payload["target_locations"] == ["NY"]

    def test_no_text_pdf_rejected(self, client):
        response = client.post(
            "/api/profile",
            files={"resume": ("scan.pdf", b"not a pdf", "application/pdf")},
        )
        assert response.status_code == 422

    def test_manual_skills_saved_without_resume(self, client):
        """006-E: editing the skills field directly (no resume upload in
        this request) must save exactly what was typed."""
        response = client.post("/api/profile", data={"skills": "Python, Rust, i2c"})
        assert response.status_code == 200
        payload = client.get("/api/profile").json()
        assert payload["skills"] == ["Python", "Rust", "i2c"]

    def test_resume_upload_extraction_merges_with_manual_skills(self, client):
        """006-E: if a resume is uploaded in the same request as an edited
        skills field, nothing should be lost — union of both, manual first."""
        response = client.post(
            "/api/profile",
            files={"resume": ("resume.pdf", self._pdf(), "application/pdf")},
            data={"skills": "Rust, Go"},
        )
        assert response.status_code == 200
        payload = client.get("/api/profile").json()
        assert "Rust" in payload["skills"]
        assert "Go" in payload["skills"]
        # extraction itself may find nothing without an LLM key — the point
        # is the manual entries are never dropped
        assert payload["skills"][:2] == ["Rust", "Go"]

    def test_resume_upload_stores_original_file(self, client):
        """007-T013 (FR-001): the original PDF bytes must survive upload —
        Apply Assist attaches the file itself, not the extracted text."""
        from engine import db, paths

        response = client.post(
            "/api/profile",
            files={"resume": ("resume.pdf", self._pdf(), "application/pdf")},
        )
        assert response.status_code == 200
        payload = client.get("/api/profile").json()
        assert payload["has_resume_file"] is True
        stored = db.get_profile()["resume_file_path"]
        assert stored is not None
        from pathlib import Path

        stored_path = Path(stored)
        assert stored_path.exists() and stored_path.stat().st_size > 0
        assert paths.data_dir() in stored_path.parents
        # server-local path never leaks into the API payload
        assert "resume_file_path" not in payload

    def test_upload_extracts_sections_when_tier_available(self, client, monkeypatch):
        """007-T013 (FR-016): extraction runs on upload and lands in the
        payload; no prior edits -> no conflict flag."""
        from engine import resume_extract
        from engine.resume_extract import ResumeSections

        monkeypatch.setattr(
            resume_extract, "extract",
            lambda text: ResumeSections(skills=["python"]),
        )
        response = client.post(
            "/api/profile",
            files={"resume": ("resume.pdf", self._pdf(), "application/pdf")},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["extraction_conflict"] is False
        assert body["resume_sections"]["skills"] == ["python"]

    def test_upload_with_edited_sections_flags_conflict(self, client, monkeypatch):
        """007-T013 (FR-016 + clarification): user-edited sections are
        never silently overwritten — re-upload flags the conflict and
        keeps the edits until the user explicitly chooses."""
        from engine import db, resume_extract
        from engine.resume_extract import ResumeSections

        db.save_profile(
            resume_sections={"experience": [], "education": [], "projects": [],
                             "skills": ["edited-by-hand"]},
            sections_edited_at="2026-07-21 10:00:00.000000",
        )
        monkeypatch.setattr(
            resume_extract, "extract",
            lambda text: ResumeSections(skills=["freshly-extracted"]),
        )
        response = client.post(
            "/api/profile",
            files={"resume": ("resume.pdf", self._pdf(), "application/pdf")},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["extraction_conflict"] is True
        assert body["resume_sections"]["skills"] == ["edited-by-hand"]  # kept

    def test_put_resume_sections_validates_and_stamps_edit_time(self, client):
        """007-T013 (FR-017): manual section editing — full replace,
        schema-validated, sections_edited_at stamped."""
        good = {"experience": [], "education": [], "projects": [], "skills": ["rust"]}
        response = client.put("/api/profile/resume-sections", json=good)
        assert response.status_code == 200
        payload = client.get("/api/profile").json()
        assert payload["resume_sections"]["skills"] == ["rust"]
        assert payload["sections_edited_at"] is not None

        bad = {"experience": "not-a-list"}
        assert client.put("/api/profile/resume-sections", json=bad).status_code == 422

    def test_reextract_requires_resume_and_consents(self, client, monkeypatch):
        """007-T013 (FR-016): explicit re-extract replaces edited sections
        and clears the edit stamp; 409 without a resume; graceful reply
        without an AI tier."""
        from engine import db, resume_extract
        from engine.resume_extract import ResumeSections

        assert client.post("/api/profile/reextract").status_code == 409

        client.post(
            "/api/profile",
            files={"resume": ("resume.pdf", self._pdf(), "application/pdf")},
        )
        client.put(
            "/api/profile/resume-sections",
            json={"experience": [], "education": [], "projects": [], "skills": ["edited"]},
        )
        monkeypatch.setattr(
            resume_extract, "extract",
            lambda text: ResumeSections(skills=["re-extracted"]),
        )
        response = client.post("/api/profile/reextract")
        assert response.status_code == 200
        payload = client.get("/api/profile").json()
        assert payload["resume_sections"]["skills"] == ["re-extracted"]
        assert payload["sections_edited_at"] is None

        monkeypatch.setattr(resume_extract, "extract", lambda text: None)
        body = client.post("/api/profile/reextract").json()
        assert body == {"extracted": False, "reason": "no-ai-tier"}

    def test_resume_pdf_download_and_409(self, client):
        """007-T018 (FR-018): tailored/untailored resume PDF download;
        409 when no sections exist yet."""
        from engine import db

        job = seed_job(url="https://example.com/pdf1")
        assert client.get(f"/api/jobs/{job['id']}/resume-pdf").status_code == 409

        db.save_profile(
            first_name="Ada", last_name="Lovelace",
            resume_sections={"experience": [], "education": [], "projects": [],
                             "skills": ["python"]},
        )
        response = client.get(f"/api/jobs/{job['id']}/resume-pdf")
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("application/pdf")
        assert "attachment" in response.headers.get("content-disposition", "")
        assert response.content[:5] == b"%PDF-"

    def test_cover_letter_pdf_download_and_409(self, client):
        """007-T018: cover-letter PDF needs tailoring output first."""
        import json as _json

        from engine import db

        job = seed_job(url="https://example.com/pdf2")
        assert client.get(f"/api/jobs/{job['id']}/cover-letter-pdf").status_code == 409

        db.save_profile(first_name="Ada", last_name="Lovelace")
        db.set_tailor(job["id"], _json.dumps({
            "summary_line": "s", "tailored_bullets": ["b"],
            "cover_letter": "Dear team — I build firmware.", "ats_keywords": [],
        }))
        response = client.get(f"/api/jobs/{job['id']}/cover-letter-pdf")
        assert response.status_code == 200
        assert response.content[:5] == b"%PDF-"

    def test_identity_fields_saved(self, client):
        """006-A: first/last name, email, phone, LinkedIn, portfolio — the
        fields Apply Assist needs but the schema never had until now."""
        response = client.post(
            "/api/profile",
            data={
                "first_name": "Ada", "last_name": "Lovelace",
                "email": "ada@example.com", "phone": "555-0100",
                "linkedin_url": "https://linkedin.com/in/ada",
                "portfolio_url": "https://ada.example.com",
            },
        )
        assert response.status_code == 200
        payload = client.get("/api/profile").json()
        assert payload["first_name"] == "Ada"
        assert payload["last_name"] == "Lovelace"
        assert payload["email"] == "ada@example.com"
        assert payload["phone"] == "555-0100"
        assert payload["linkedin_url"] == "https://linkedin.com/in/ada"
        assert payload["portfolio_url"] == "https://ada.example.com"

    def test_sponsorship_and_visa_fields_saved(self, client):
        """005-T036: Profile page collects the facts answer_bank.suggest()
        needs to ground drafted sponsorship/work-authorization answers."""
        response = client.post(
            "/api/profile",
            data={
                "authorized_without_sponsorship": "no",
                "visa_status": "OPT",
            },
        )
        assert response.status_code == 200
        payload = client.get("/api/profile").json()
        assert payload["authorized_without_sponsorship"] == "no"
        assert payload["visa_status"] == "OPT"


class TestExportApi:
    def test_csv_of_current_filter(self, client):
        seed_job(url="https://example.com/1", title="Export Me")
        seed_job(url="https://example.com/2", title="Austin Job", location="Austin, TX")
        response = client.get("/api/export", params={"location": "Austin"})
        assert response.status_code == 200
        assert "text/csv" in response.headers["content-type"]
        assert "attachment" in response.headers.get("content-disposition", "")
        body = response.text
        assert "Austin Job" in body
        assert "Export Me" not in body  # filter respected


class TestStagesApi:
    def test_stage_roundtrip_and_errors(self, client):
        job = seed_job()
        client.post(f"/api/jobs/{job['id']}/status", json={"status": "applied"})
        ok = client.post(f"/api/jobs/{job['id']}/stage", params={"stage": "interview"})
        assert ok.status_code == 200
        assert ok.json()["stage"] == "interview"
        assert client.post(
            f"/api/jobs/{job['id']}/stage", params={"stage": "bogus"}
        ).status_code == 400
        assert client.post(
            "/api/jobs/99999/stage", params={"stage": "oa"}
        ).status_code == 404

    def test_notes_endpoint(self, client):
        job = seed_job()
        response = client.post(
            f"/api/jobs/{job['id']}/notes", data={"notes": "recruiter call Tuesday"}
        )
        assert response.status_code == 200
        detail = client.get(f"/api/jobs/{job['id']}").json()
        assert detail["notes"] == "recruiter call Tuesday"

    def test_analytics_endpoint_shape(self, client):
        job = seed_job()
        client.post(f"/api/jobs/{job['id']}/status", json={"status": "applied"})
        stats = client.get("/api/analytics").json()
        assert stats["total_applied"] == 1
        assert "by_source" in stats and "by_band" in stats

    def test_analytics_page_serves(self, client):
        assert client.get("/analytics").status_code == 200


class TestRefreshApi:
    def test_start_then_cooldown_then_force(self, client):
        first = client.post("/api/refresh")
        assert first.status_code == 200
        assert first.json()["started"] is True

        second = client.post("/api/refresh")
        assert second.json()["started"] is False
        assert second.json()["reason"] in ("cooldown", "running")

        forced = client.post("/api/refresh", params={"force": 1})
        assert forced.json()["started"] is True

    def test_status_endpoint_shape(self, client):
        client.post("/api/refresh")
        status = client.get("/api/refresh/status").json()
        assert "active" in status and "sources" in status
