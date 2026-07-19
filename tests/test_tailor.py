"""004-WS-B: per-job tailored resume bullets + cover letter."""
import json

import pytest
from fastapi.testclient import TestClient

from engine import db, settings, tailor

VALID = json.dumps(
    {
        "summary_line": "Computer engineering new grad with FPGA verification focus.",
        "tailored_bullets": [
            "Built a UVM testbench for an ALU, mirroring this role's verification flow",
            "Prototyped a RISC-V core on FPGA using SystemVerilog",
        ],
        "cover_letter": "Dear team, ... (about 180 words)",
        "ats_keywords": ["SystemVerilog", "UVM", "FPGA"],
    }
)


@pytest.fixture()
def client(tmp_db, monkeypatch):
    monkeypatch.setenv("REFRESH_SYNC", "1")
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    from engine import pipeline

    monkeypatch.setattr(pipeline, "_source_names", lambda: [])
    monkeypatch.setattr(pipeline, "load_companies", lambda: [])
    from web.main import create_app

    return TestClient(create_app())


def seed_job():
    db.upsert_job(
        {"title": "DV Engineer", "company": "ChipCo",
         "url": "https://x.example/dv", "source": "greenhouse",
         "description": "UVM SystemVerilog verification"}
    )
    jobs, _ = db.query_jobs(window=None, statuses=None, entry_level=None)
    return jobs[0]["id"]


class TestTailorEngine:
    def test_valid_response_parsed(self, tmp_db, monkeypatch):
        monkeypatch.setenv("LLM_API_KEY", "k")
        monkeypatch.setattr(tailor.matcher, "_chat", lambda m: VALID)
        result = tailor.tailor_for_job("resume text", "DV Engineer", "ChipCo", "jd")
        assert result is not None
        assert len(result.tailored_bullets) == 2

    def test_prompt_contains_no_invention_guard_and_inputs(self, tmp_db, monkeypatch):
        monkeypatch.setenv("LLM_API_KEY", "k")
        captured = {}

        def chat(messages):
            captured["all"] = json.dumps(messages)
            return VALID

        monkeypatch.setattr(tailor.matcher, "_chat", chat)
        tailor.tailor_for_job("MY REAL RESUME", "DV Engineer", "ChipCo", "THE JD TEXT")
        assert "never invent" in captured["all"].lower()
        assert "MY REAL RESUME" in captured["all"]
        assert "THE JD TEXT" in captured["all"]

    def test_invalid_twice_returns_none(self, tmp_db, monkeypatch):
        monkeypatch.setenv("LLM_API_KEY", "k")
        monkeypatch.setattr(tailor.matcher, "_chat", lambda m: "not json")
        assert tailor.tailor_for_job("r", "t", "c", "d") is None


class TestTailorApi:
    def test_requires_resume_then_key(self, client):
        job_id = seed_job()
        assert client.post(f"/api/jobs/{job_id}/tailor").status_code == 409  # no resume
        db.save_profile(resume_text="resume", resume_filename="r.pdf")
        assert client.post(f"/api/jobs/{job_id}/tailor").status_code == 409  # no key

    def test_tailor_stored_and_returned(self, client, monkeypatch):
        job_id = seed_job()
        db.save_profile(resume_text="resume", resume_filename="r.pdf")
        settings.set("LLM_API_KEY", "k")
        monkeypatch.setattr(tailor.matcher, "_chat", lambda m: VALID)
        response = client.post(f"/api/jobs/{job_id}/tailor")
        assert response.status_code == 200
        assert "SystemVerilog" in response.json()["ats_keywords"]
        assert db.get_job(job_id)["tailor_json"] is not None

    def test_resume_reupload_clears_cached_tailoring(self, client, monkeypatch):
        job_id = seed_job()
        db.save_profile(resume_text="resume", resume_filename="r.pdf")
        settings.set("LLM_API_KEY", "k")
        monkeypatch.setattr(tailor.matcher, "_chat", lambda m: VALID)
        client.post(f"/api/jobs/{job_id}/tailor")
        db.save_profile(resume_text="a different resume")
        assert db.get_job(job_id)["tailor_json"] is None

    def test_unknown_job_404(self, client):
        db.save_profile(resume_text="resume")
        settings.set("LLM_API_KEY", "k")
        assert client.post("/api/jobs/99999/tailor").status_code == 404
