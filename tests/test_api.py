"""T009: HTTP contract tests per contracts/http-api.md (US1 endpoints)."""
import pytest
from fastapi.testclient import TestClient

from engine import db


@pytest.fixture()
def client(tmp_db, monkeypatch):
    # Refresh runs synchronously (and fetches nothing) so tests are deterministic.
    monkeypatch.setenv("REFRESH_SYNC", "1")
    from engine import pipeline

    monkeypatch.setattr(pipeline, "_source_names", lambda: [])
    monkeypatch.setattr(pipeline, "load_companies", lambda: [])
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
