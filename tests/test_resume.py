"""T031: PDF text extraction and the no-text error path."""
import fitz
import pytest

from engine import resume


def make_pdf(text: str) -> bytes:
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), text)
    return doc.tobytes()


class TestExtractText:
    def test_extracts_text(self):
        pdf = make_pdf(
            "ABHINAV B\nComputer Engineering, 2026\n"
            "Skills: Python, Verilog, FPGA, embedded C"
        )
        text = resume.extract_text(pdf)
        assert "Verilog" in text
        assert "Computer Engineering" in text

    def test_scanned_pdf_without_text_raises(self):
        doc = fitz.open()
        doc.new_page()  # blank page, no extractable text
        with pytest.raises(resume.NoTextError):
            resume.extract_text(doc.tobytes())

    def test_garbage_bytes_raise(self):
        with pytest.raises(resume.NoTextError):
            resume.extract_text(b"this is not a pdf")
