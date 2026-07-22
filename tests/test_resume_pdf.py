"""007-T016: engine/resume_pdf.py — fpdf2 rendering of tailored resume +
cover-letter PDFs, with a fingerprint cache that can never serve a stale
document (FR-018/FR-019/FR-020)."""
import json

import fitz
import pytest

from engine import db, resume_pdf


IDENTITY = {
    "first_name": "Ada", "last_name": "Lovelace",
    "email": "ada@example.com", "phone": "555-0100",
    "linkedin_url": "https://linkedin.com/in/ada",
    "portfolio_url": "https://ada.example.com",
}

SECTIONS = {
    "experience": [
        {
            "title": "Firmware Intern",
            "organization": "Acme Robotics",
            "start": "2025-05",
            "end": "2025-08",
            "bullets": ["Wrote STM32 drivers — cut boot time 40%"],
        }
    ],
    "education": [
        {
            "degree": "B.S. Computer Engineering",
            "institution": "État University",  # unicode on purpose
            "start": "2022-08",
            "end": "2026-05",
            "details": "GPA 3.8",
        }
    ],
    "projects": [
        {
            "name": "RISC-V core",
            "description": "5-stage pipelined core",
            "bullets": ["Passed rv32i compliance suite"],
        }
    ],
    "skills": ["python", "verilog", "i2c"],
}

TAILORING = {
    "summary_line": "Embedded engineer tuned for Acme's firmware role",
    "tailored_bullets": ["Shipped I2C sensor drivers on STM32"],
    "cover_letter": "Dear team — I build firmware.",
    "ats_keywords": ["firmware", "i2c"],
}


def pdf_text(data: bytes) -> str:
    with fitz.open(stream=data, filetype="pdf") as doc:
        return "\n".join(page.get_text() for page in doc)


class TestRenderResume:
    def test_renders_parseable_single_column_pdf(self):
        data = resume_pdf.render_resume(SECTIONS, IDENTITY, tailoring=None)
        text = pdf_text(data)
        assert "Ada Lovelace" in text
        assert "ada@example.com" in text
        assert "Firmware Intern" in text
        assert "Acme Robotics" in text
        assert "RISC-V core" in text
        assert "python" in text

    def test_unicode_renders(self):
        """en-dash in a bullet + accented institution — fpdf2 core fonts
        would raise/garble; the bundled DejaVu face must handle both."""
        data = resume_pdf.render_resume(SECTIONS, IDENTITY, tailoring=None)
        text = pdf_text(data)
        assert "État University" in text
        assert "cut boot time 40%" in text

    def test_tailored_variant_leads_with_tailoring(self):
        data = resume_pdf.render_resume(SECTIONS, IDENTITY, tailoring=TAILORING)
        text = pdf_text(data)
        assert "Embedded engineer tuned for Acme's firmware role" in text
        assert "Shipped I2C sensor drivers on STM32" in text
        # structured sections still present — tailoring supplements, never replaces
        assert "Firmware Intern" in text

    def test_render_requires_sections(self):
        with pytest.raises(ValueError):
            resume_pdf.render_resume(None, IDENTITY, tailoring=None)


class TestRenderCoverLetter:
    def test_cover_letter_pdf(self):
        data = resume_pdf.render_cover_letter(
            IDENTITY, "Acme Robotics", "Firmware Engineer",
            TAILORING["cover_letter"],
        )
        text = pdf_text(data)
        assert "Dear team" in text
        assert "Ada Lovelace" in text


class TestTailoredCache:
    def _seed_job_with_tailoring(self):
        from tests.test_db import make_job

        db.upsert_job(make_job(url="pdfjob"))
        jobs, _ = db.query_jobs(window=None, statuses=None)
        job = next(j for j in jobs if j["url"] == "pdfjob")
        db.set_tailor(job["id"], json.dumps(TAILORING))
        return job["id"]

    def test_cache_hit_and_invalidation(self, tmp_db):
        db.save_profile(resume_sections=SECTIONS, **IDENTITY)
        job_id = self._seed_job_with_tailoring()

        path1 = resume_pdf.tailored_resume_path(job_id)
        assert path1.exists()
        first_mtime = path1.stat().st_mtime_ns
        # unchanged inputs -> same file, no re-render
        path2 = resume_pdf.tailored_resume_path(job_id)
        assert path2.stat().st_mtime_ns == first_mtime

        # changing the sections invalidates the fingerprint -> re-render
        changed = dict(SECTIONS, skills=["python", "rust"])
        db.save_profile(resume_sections=changed)
        path3 = resume_pdf.tailored_resume_path(job_id)
        assert "rust" in pdf_text(path3.read_bytes())

    def test_no_sections_raises(self, tmp_db):
        job_id = self._seed_job_with_tailoring()
        with pytest.raises(ValueError):
            resume_pdf.tailored_resume_path(job_id)
