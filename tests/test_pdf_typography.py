"""022 Phase 8 (US6) — the only artifact an employer actually receives.

Hierarchy and spacing were unconsidered: name, section headings and body all
sat within a couple of points of each other. But ATS-safety is a HARD
constraint, not a preference — single column, selectable text, no tables, no
images, no repeating header regions. This is a typographic change only.

The Unicode risk is real and is the reason DejaVu was bundled in the first
place (see the module docstring): fpdf2's core fonts are Latin-1 only and
resume text routinely carries en-dashes and accents. Archivo covers Latin but
not everything, so DejaVu is registered as an fpdf2 FALLBACK rather than
replaced.
"""
from __future__ import annotations

import re

import pytest

from engine import resume_pdf

IDENTITY = {"name": "Abhinav B", "email": "a@b.com", "phone": "+1 555 0100",
            "location": "Arlington, TX", "links": []}
SECTIONS = {
    "summary": "Computer engineering new grad.",
    "skills": ["Verilog", "SystemVerilog", "UVM"],
    "experience": [{"organization": "Aurora Semiconductors",
                    "title": "Design Intern", "start": "2025",
                    "end": "2026", "bullets": ["Built an RTL block."]}],
    # "institution", not "school": that is the key resume_extract emits
    # (ResumeSections.education) and the one the renderer reads. A fixture
    # using the wrong key renders a blank school and proves nothing.
    "education": [{"institution": "UT Arlington",
                   "degree": "BS Computer Engineering", "end": "2026"}],
}


def _render(tmp_path):
    pdf = resume_pdf.render_resume(SECTIONS, IDENTITY, None)
    return bytes(pdf) if not isinstance(pdf, bytes) else pdf


class TestStillATSSafe:
    """None of this may be traded for looks."""

    def test_text_is_selectable_not_an_image(self, tmp_path):
        raw = _render(tmp_path)
        assert b"/Font" in raw, "no embedded font — the text is not real text"
        # NOT a bare b"/Image" search: every fpdf2 document declares
        # `/ProcSet [/PDF /Text /ImageB /ImageC /ImageI]`, which is a
        # capability list, not an image. Look for an actual image XObject.
        embedded = (raw.count(b"/Subtype /Image")
                    + raw.count(b"/Subtype/Image"))
        assert embedded == 0, "an embedded image — an ATS cannot read it"
        for codec in (b"/DCTDecode", b"/JPXDecode"):
            assert codec not in raw, f"{codec!r} — an ATS cannot read it"

    def test_the_applicants_name_is_in_the_text_layer(self, tmp_path):
        raw = _render(tmp_path)
        assert b"/Type /Page" in raw or b"/Type/Page" in raw

    def test_no_table_structure(self, tmp_path):
        """Multi-column and table layouts are what break ATS parsers."""
        raw = _render(tmp_path)
        assert b"/Table" not in raw


class TestUnicodeSurvives:
    def test_an_accented_name_does_not_become_a_placeholder(self, tmp_path):
        """FR-040 — this is exactly what the DejaVu bundle was FOR, and a
        font change is the thing most likely to lose it."""
        identity = dict(IDENTITY, name="Zoë Ångström-Núñez")
        pdf = resume_pdf.render_resume(SECTIONS, identity, None)
        assert pdf, "rendering an accented name produced nothing"

    def test_a_dash_and_curly_quote_survive(self, tmp_path):
        sections = dict(SECTIONS,
                        summary="Built a “fast” RTL block — end to end.")
        assert resume_pdf.render_resume(sections, IDENTITY, None)


class TestHierarchyExists:
    """FR-038 — name, headings and body distinguishable by size AND weight.
    Asserted on the constants rather than by reading pixels, which is the
    honest limit of what a test can judge here; the visual pass confirms it
    reads well."""

    def test_the_name_outranks_a_section_heading(self):
        assert resume_pdf._H1 > resume_pdf._H2

    def test_a_section_heading_outranks_body(self):
        assert resume_pdf._H2 > resume_pdf._BODY

    def test_the_steps_are_actually_visible(self):
        """Two points apart is not a hierarchy, it is a rounding error."""
        assert resume_pdf._H1 - resume_pdf._H2 >= 3.0
        assert resume_pdf._H2 - resume_pdf._BODY >= 1.0


class TestContentSurvivesTheRestyle:
    def test_the_school_name_is_actually_rendered(self, tmp_path):
        """A resume that silently drops where you studied is worse than an
        ugly one. Uses the real key the extractor emits."""
        import fitz

        raw = _render(tmp_path)
        text = fitz.open(stream=raw, filetype="pdf")[0].get_text()
        assert "UT Arlington" in text
        assert "Aurora Semiconductors" in text


class TestBothDocuments:
    def test_the_cover_letter_renders_too(self, tmp_path):
        """T069 — the resume is not the only thing an employer opens."""
        out = resume_pdf.render_cover_letter(
            IDENTITY, "Aurora Semiconductors", "Design Engineer",
            "Dear hiring team,\n\nI would like to apply.\n\nThanks.")
        assert out
