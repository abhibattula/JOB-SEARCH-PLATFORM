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

    def test_applied_board_view_renders_stage_columns(self, client):
        """007-T038 (FR-025): the Applied view offers a stage-column board
        with counts; the table stays available as a toggle."""
        job = seed_job()
        client.post(f"/api/jobs/{job['id']}/status", json={"status": "applied"})
        client.post(f"/api/jobs/{job['id']}/stage", params={"stage": "interview"})

        board = client.get("/", params={"status": "applied", "view": "board"})
        assert board.status_code == 200
        assert 'class="board"' in board.text
        for stage in ("applied", "oa", "interview", "offer", "rejected"):
            assert f'data-stage="{stage}"' in board.text
        assert "Software Engineer, New Grad" in board.text
        # move buttons (the keyboard/AT path) present on cards
        assert "board-move" in board.text

        table = client.get("/", params={"status": "applied"})
        assert 'class="board"' not in table.text  # table remains the default
        assert "view=board" in table.text  # toggle offered

    def test_onboarding_checklist_reflects_real_state(self, client):
        """007-T040 (FR-027): checklist derives from actual completion
        state — no stored step flags that can drift from reality."""
        from engine import db

        fresh = client.get("/")
        assert "onboarding-checklist" in fresh.text
        assert "Upload your resume" in fresh.text

        db.save_profile(resume_text="resume", resume_filename="r.pdf")
        after_resume = client.get("/")
        # the resume step now renders as done (✓) — state is derived live
        assert 'class="ob-step done"' in after_resume.text

    def test_onboarding_checklist_dismissible(self, client):
        from engine import settings

        settings.set("ONBOARDING_DISMISSED", "1")
        resp = client.get("/")
        assert "onboarding-checklist" not in resp.text

    def test_feed_action_buttons_have_accessible_names(self, client):
        """007-T042 (FR-028): icon-only ☆ ✓ ✕ controls expose aria-labels."""
        seed_job()
        resp = client.get("/")
        assert 'aria-label="Save' in resp.text
        assert 'aria-label="Mark applied' in resp.text
        assert 'aria-label="Hide' in resp.text

    def test_polled_regions_are_aria_live(self, client):
        resp = client.get("/")
        assert 'aria-live="polite"' in resp.text

    @pytest.mark.parametrize("theme", ["light", "dark"])
    def test_all_pages_render_in_both_themes(self, client, theme):
        """007-T043 (FR-021): every page renders under both themes with the
        chosen theme stamped on the document."""
        from engine import settings

        settings.set("THEME", theme)
        job = seed_job()
        for path in ("/", "/analytics", "/profile", "/settings", "/autofill",
                     f"/jobs/{job['id']}"):
            resp = client.get(path)
            assert resp.status_code == 200, path
            assert f'data-theme="{theme}"' in resp.text, path

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


class TestSponsorIntelligenceApi:
    def _grade_company(self, name, grade=None, cap=0, wage=None, offered=None, denials=0):
        with db._conn() as conn:
            cid = db._get_or_create_company(conn, name)
            conn.execute(
                "UPDATE companies SET sponsor_grade=?, cap_exempt=?,"
                " wage_level_median=?, wage_offered_median=?, h1b_denials=?"
                " WHERE id=?",
                (grade, cap, wage, offered, denials, cid),
            )

    def test_feed_rows_carry_grade_and_cap_exempt(self, client):
        """007-T035 (FR-011/012): grade + cap-exempt in the jobs payload."""
        seed_job(url="https://example.com/g1", company="GradeCo")
        self._grade_company("GradeCo", grade="A", cap=0)
        seed_job(url="https://example.com/u1", company="State University")
        self._grade_company("State University", grade=None, cap=1)

        payload = client.get("/api/jobs").json()
        by_company = {j["company"]: j for j in payload["jobs"]}
        assert by_company["GradeCo"]["sponsor_grade"] == "A"
        assert by_company["GradeCo"]["cap_exempt"] is False
        assert by_company["State University"]["sponsor_grade"] is None
        assert by_company["State University"]["cap_exempt"] is True

    def test_strong_sponsors_filter(self, client):
        """007-T035 (FR-014): grade >= B or cap-exempt; composes with
        existing filters."""
        seed_job(url="https://example.com/a", title="A Job", company="ACo")
        self._grade_company("ACo", grade="A")
        seed_job(url="https://example.com/c", title="C Job", company="CCo")
        self._grade_company("CCo", grade="C")
        seed_job(url="https://example.com/u", title="Uni Job", company="State University")
        self._grade_company("State University", cap=1)
        seed_job(url="https://example.com/n", title="No Data Job", company="NoCo")

        narrowed = client.get("/api/jobs", params={"strong_sponsors": 1}).json()
        titles = {j["title"] for j in narrowed["jobs"]}
        assert titles == {"A Job", "Uni Job"}
        # composes with existing params
        composed = client.get(
            "/api/jobs", params={"strong_sponsors": 1, "location": "San Francisco"}
        ).json()
        assert composed["total"] == 2  # both seeded in SF by default

    def test_detail_includes_sponsor_evidence(self, client):
        """007-T035 (FR-015): the evidence panel object."""
        job = seed_job(url="https://example.com/e1", company="GradeCo")
        self._grade_company("GradeCo", grade="B", cap=0, wage="III",
                            offered=150000.0, denials=12)

        detail = client.get(f"/api/jobs/{job['id']}").json()
        evidence = detail["sponsor_evidence"]
        assert evidence["grade"] == "B"
        assert evidence["denials"] == 12
        assert evidence["wage_level_median"] == "III"
        assert evidence["wage_offered_median"] == 150000.0
        assert evidence["cap_exempt"] is False
        assert "lottery_hint" in evidence


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


class Test008ShellSupport:
    """008 US2 (T014): host-side open-in-system-browser and clipboard
    endpoints — the pywebview shell's guaranteed paths for external links
    and copying (FR-002/FR-004)."""

    def test_open_launches_system_browser(self, client, monkeypatch):
        import webbrowser

        opened = []
        monkeypatch.setattr(webbrowser, "open", lambda url: opened.append(url) or True)
        resp = client.post("/api/open", json={"url": "https://example.com/job"})
        assert resp.status_code == 200
        assert resp.json() == {"opened": True}
        assert opened == ["https://example.com/job"]

    def test_open_rejects_non_http_schemes(self, client, monkeypatch):
        import webbrowser

        monkeypatch.setattr(
            webbrowser, "open",
            lambda url: (_ for _ in ()).throw(AssertionError("must not open")),
        )
        for bad in ("file:///C:/Windows/system32", "javascript:alert(1)", "notaurl"):
            resp = client.post("/api/open", json={"url": bad})
            assert resp.status_code == 400, bad

    def test_clipboard_copies_via_engine_helper(self, client, monkeypatch):
        from engine import clipboard

        copied = []
        monkeypatch.setattr(clipboard, "copy_text", lambda text: copied.append(text))
        resp = client.post("/api/clipboard", json={"text": "Design Verification Engineer"})
        assert resp.status_code == 200
        assert resp.json() == {"copied": True}
        assert copied == ["Design Verification Engineer"]

    def test_clipboard_failure_is_honest(self, client, monkeypatch):
        from engine import clipboard

        def boom(text):
            raise RuntimeError("no clipboard mechanism available")

        monkeypatch.setattr(clipboard, "copy_text", boom)
        resp = client.post("/api/clipboard", json={"text": "x"})
        assert resp.status_code == 500
        assert "clipboard" in resp.json()["detail"].lower()


class Test008CrashMarker:
    """008 US2 (T021): a crash in the previous run surfaces once."""

    def test_crash_marker_shows_notice_once_then_clears(self, client, tmp_path):
        from engine import paths

        marker = paths.data_dir() / "crash.marker"
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text("2026-07-22", encoding="utf-8")
        first = client.get("/")
        assert first.status_code == 200
        assert "closed unexpectedly" in first.text
        assert not marker.exists()
        second = client.get("/")
        assert "closed unexpectedly" not in second.text


class Test008CopyAffordances:
    """008 US2 (T019/T020): copy-link buttons everywhere, and no template
    may use raw navigator.clipboard (dead inside the WebView2 shell)."""

    def test_feed_row_has_copy_link_button(self, client):
        job = seed_job()
        resp = client.get("/partials/feed")
        assert resp.status_code == 200
        assert f'copyText({job["url"]!r}' in resp.text.replace("&#39;", "'")

    def test_job_detail_has_copy_link_and_visible_url(self, client):
        job = seed_job()
        resp = client.get(f"/jobs/{job['id']}")
        assert resp.status_code == 200
        text = resp.text.replace("&#39;", "'")
        assert f'copyText({job["url"]!r}' in text
        assert "Copy link" in resp.text

    def test_no_template_uses_navigator_clipboard_inline(self):
        from pathlib import Path

        offenders = [
            str(path)
            for path in Path("web/templates").rglob("*.html")
            if "navigator.clipboard" in path.read_text(encoding="utf-8")
        ]
        assert offenders == []


class Test008FeedControls:
    """008 US3 (T033/T034): default 2-week window, source filter, paging,
    immediate sort, honest approximate dates."""

    def test_default_window_is_14d(self):
        from web.routes_api import parse_feed_params

        assert parse_feed_params()["window"] == "14d"

    def test_page_param_maps_to_offset(self):
        from web.routes_api import parse_feed_params

        params = parse_feed_params(page=3)
        assert params["offset"] == 200 and params["limit"] == 100

    def test_source_param_passes_through(self):
        from web.routes_api import parse_feed_params

        assert parse_feed_params(source="greenhouse")["source"] == "greenhouse"
        assert parse_feed_params()["source"] is None

    def test_feed_page_has_two_week_default_sort_autosubmit_and_source_select(
        self, client
    ):
        seed_job()
        resp = client.get("/")
        assert resp.status_code == 200
        assert "2 weeks" in resp.text
        assert 'name="source"' in resp.text
        assert "this.form.submit()" in resp.text  # sort applies immediately

    def test_window_links_preserve_other_filters(self, client):
        seed_job()
        resp = client.get("/?location=Austin&remote=1&sort=date")
        assert resp.status_code == 200
        text = resp.text.replace("&amp;", "&")
        # the window segmented links carry the location/remote/sort state
        assert "window=24h" in text
        start = text.index("window=24h")
        snippet = text[max(0, start - 200): start + 200]
        assert "location=Austin" in snippet

    def test_pager_appears_beyond_one_page(self, client):
        for i in range(3):
            seed_job(url=f"https://example.com/p/{i}", title=f"Role {i}")
        resp = client.get("/partials/feed?limit=2")
        assert "page 1 of 2" in resp.text.lower()

    def test_unknown_posted_date_marked_approximate(self, client):
        seed_job(url="https://example.com/nodate", posted_date=None)
        resp = client.get("/partials/feed")
        assert "seen ~" in resp.text or "≈" in resp.text


class Test008Watchlist:
    """008 US3 (T029): company watchlist CRUD per contracts/http-api.md."""

    def test_crud_roundtrip(self, client):
        resp = client.post("/api/watchlist",
                           json={"ats": "greenhouse", "slug": "sifive", "name": "SiFive"})
        assert resp.status_code == 201
        row = resp.json()
        assert row["origin"] == "user" and row["enabled"] is True

        assert client.post(
            "/api/watchlist", json={"ats": "greenhouse", "slug": "sifive"}
        ).status_code == 409
        assert client.post(
            "/api/watchlist", json={"ats": "bogus", "slug": "x"}
        ).status_code == 400

        listing = client.get("/api/watchlist").json()["companies"]
        assert any(c["slug"] == "sifive" for c in listing)

        resp = client.patch(f"/api/watchlist/{row['id']}", json={"enabled": False})
        assert resp.status_code == 200
        listing = client.get("/api/watchlist").json()["companies"]
        assert next(c for c in listing if c["id"] == row["id"])["enabled"] is False

        assert client.delete(f"/api/watchlist/{row['id']}").json()["result"] == "deleted"
        listing = client.get("/api/watchlist").json()["companies"]
        assert not any(c["id"] == row["id"] for c in listing)

    def test_delete_shipped_row_disables_instead(self, client, tmp_path, monkeypatch):
        seed = tmp_path / "companies.yml"
        seed.write_text(
            "companies:\n  - {name: Stripe, ats: greenhouse, slug: stripe}\n",
            encoding="utf-8",
        )
        monkeypatch.setenv("COMPANIES_PATH", str(seed))
        from engine import watchlist

        watchlist.ensure_seeded()
        row = next(c for c in client.get("/api/watchlist").json()["companies"]
                   if c["slug"] == "stripe")
        assert client.delete(f"/api/watchlist/{row['id']}").json()["result"] == "disabled"
        listing = client.get("/api/watchlist").json()["companies"]
        assert next(c for c in listing if c["id"] == row["id"])["enabled"] is False

    def test_settings_page_shows_watchlist_section(self, client):
        resp = client.get("/settings")
        assert resp.status_code == 200
        assert "Company watchlist" in resp.text


class Test008LinkedInLinkout:
    def test_job_linkedin_url_route(self, client):
        job = seed_job(title="ASIC Engineer New Grad")
        resp = client.get(f"/api/jobs/{job['id']}/linkedin-url")
        assert resp.status_code == 200
        assert "linkedin.com/jobs/search" in resp.json()["url"]
        assert "ASIC" in resp.json()["url"]

    def test_feed_toolbar_offers_linkedin_search(self, client):
        seed_job()
        resp = client.get("/")
        assert "Search on LinkedIn" in resp.text
