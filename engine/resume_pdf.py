"""ATS-safe resume + cover-letter PDF rendering (feature 007, US2).

fpdf2, single column, selectable text, bundled DejaVu faces (fpdf2's core
fonts are Latin-1 only — resume text routinely has en-dashes/accents).
Tailored variants lead with the job's tailoring output but always include
the user's structured sections: tailoring supplements the reviewed facts,
it never replaces them (FR-019 no-invention chain).

The per-job cache (data_dir()/tailored/<job_id>.pdf + .fingerprint) can
never serve a stale document: the fingerprint hashes the exact inputs and
any mismatch re-renders (FR-020).
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from fpdf import FPDF

from . import db, paths

_MARGIN = 18  # mm
_BODY = 10.5  # pt
_SMALL = 9.0
_H1 = 16.0
_H2 = 11.5


def _fonts_dir() -> Path:
    return paths.resource_path("assets/fonts")


class _Doc(FPDF):
    def __init__(self) -> None:
        super().__init__(format="Letter", unit="mm")
        self.set_margins(_MARGIN, _MARGIN, _MARGIN)
        self.set_auto_page_break(auto=True, margin=_MARGIN)
        fonts = _fonts_dir()
        self.add_font("DejaVu", "", str(fonts / "DejaVuSans.ttf"))
        self.add_font("DejaVu", "B", str(fonts / "DejaVuSans-Bold.ttf"))
        self.add_font("DejaVu", "I", str(fonts / "DejaVuSans-Oblique.ttf"))
        self.add_page()

    def line_out(self, text: str, size: float = _BODY, style: str = "",
                 gap: float = 1.4) -> None:
        self.set_font("DejaVu", style, size)
        self.multi_cell(0, size * 0.55, text)
        self.ln(gap)

    def heading(self, text: str) -> None:
        self.ln(2.2)
        self.set_font("DejaVu", "B", _H2)
        self.cell(0, _H2 * 0.55, text.upper(), new_x="LMARGIN", new_y="NEXT")
        y = self.get_y() + 0.8
        self.line(_MARGIN, y, self.w - _MARGIN, y)
        self.ln(2.6)


def _identity_header(pdf: _Doc, identity: dict) -> None:
    name = f"{identity.get('first_name') or ''} {identity.get('last_name') or ''}".strip()
    if name:
        pdf.line_out(name, size=_H1, style="B", gap=0.6)
    contact = " · ".join(
        v for v in (
            identity.get("email"), identity.get("phone"),
            identity.get("linkedin_url"), identity.get("portfolio_url"),
        ) if v
    )
    if contact:
        pdf.line_out(contact, size=_SMALL, gap=1.8)


def render_resume(sections: dict | None, identity: dict,
                  tailoring: dict | None) -> bytes:
    """Render the resume PDF. `sections` is the user-reviewed structured
    resume (required); `tailoring` (optional) adds the job-tuned summary
    line and bullets at the top."""
    if not sections:
        raise ValueError("no resume sections — fill in the Resume builder first")
    pdf = _Doc()
    _identity_header(pdf, identity)

    if tailoring and tailoring.get("summary_line"):
        pdf.line_out(tailoring["summary_line"], size=_BODY, style="I", gap=1.8)
    if tailoring and tailoring.get("tailored_bullets"):
        pdf.heading("Highlights for this role")
        for bullet in tailoring["tailored_bullets"]:
            pdf.line_out(f"•  {bullet}", gap=0.8)

    if sections.get("experience"):
        pdf.heading("Experience")
        for entry in sections["experience"]:
            head = " — ".join(v for v in (entry.get("title"), entry.get("organization")) if v)
            dates = " – ".join(v for v in (entry.get("start"), entry.get("end")) if v)
            pdf.line_out(head + (f"   ({dates})" if dates else ""), style="B", gap=0.5)
            for bullet in entry.get("bullets") or []:
                pdf.line_out(f"•  {bullet}", gap=0.5)
            pdf.ln(1.2)

    if sections.get("education"):
        pdf.heading("Education")
        for entry in sections["education"]:
            head = " — ".join(v for v in (entry.get("degree"), entry.get("institution")) if v)
            dates = " – ".join(v for v in (entry.get("start"), entry.get("end")) if v)
            pdf.line_out(head + (f"   ({dates})" if dates else ""), style="B", gap=0.4)
            if entry.get("details"):
                pdf.line_out(entry["details"], size=_SMALL, gap=0.8)

    if sections.get("projects"):
        pdf.heading("Projects")
        for entry in sections["projects"]:
            head = " — ".join(v for v in (entry.get("name"), entry.get("description")) if v)
            pdf.line_out(head, style="B", gap=0.5)
            for bullet in entry.get("bullets") or []:
                pdf.line_out(f"•  {bullet}", gap=0.5)
            pdf.ln(1.0)

    if sections.get("skills"):
        pdf.heading("Skills")
        pdf.line_out(", ".join(sections["skills"]))

    return bytes(pdf.output())


def render_cover_letter(identity: dict, company: str, title: str,
                        cover_letter: str) -> bytes:
    pdf = _Doc()
    _identity_header(pdf, identity)
    pdf.line_out(f"Re: {title} — {company}", style="B", gap=2.4)
    for paragraph in (cover_letter or "").split("\n"):
        if paragraph.strip():
            pdf.line_out(paragraph.strip(), gap=1.6)
    name = f"{identity.get('first_name') or ''} {identity.get('last_name') or ''}".strip()
    if name:
        pdf.ln(2)
        pdf.line_out(name)
    return bytes(pdf.output())


# --- per-job tailored cache (FR-020) ----------------------------------------


def _fingerprint(sections: dict, tailoring: dict | None) -> str:
    payload = json.dumps([sections, tailoring], sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _identity_from_profile(profile: dict) -> dict:
    return {
        key: profile.get(key)
        for key in ("first_name", "last_name", "email", "phone",
                    "linkedin_url", "portfolio_url")
    }


def tailored_resume_path(job_id: int) -> Path:
    """Path to the job's tailored resume PDF, re-rendered transparently
    whenever the underlying sections or tailoring changed. Untailored jobs
    still get a PDF from the sections alone (US2-AS6)."""
    profile = db.get_profile()
    if not profile or not profile.get("resume_sections"):
        raise ValueError("no resume sections — fill in the Resume builder first")
    job = db.get_job(job_id)
    if job is None:
        raise KeyError(f"job {job_id} not found")
    tailoring = None
    if job.get("tailor_json"):
        try:
            tailoring = json.loads(job["tailor_json"])
        except (TypeError, ValueError):
            tailoring = None

    out_dir = paths.data_dir() / "tailored"
    out_dir.mkdir(parents=True, exist_ok=True)
    pdf_path = out_dir / f"{job_id}.pdf"
    fp_path = out_dir / f"{job_id}.fingerprint"
    fingerprint = _fingerprint(profile["resume_sections"], tailoring)

    if not (pdf_path.exists() and fp_path.exists()
            and fp_path.read_text(encoding="utf-8") == fingerprint):
        data = render_resume(
            profile["resume_sections"], _identity_from_profile(profile), tailoring
        )
        pdf_path.write_bytes(data)
        fp_path.write_text(fingerprint, encoding="utf-8")
    return pdf_path
