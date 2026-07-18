"""Resume PDF text extraction (PyMuPDF). Local only — nothing leaves the machine."""
from __future__ import annotations

import fitz

MIN_TEXT_CHARS = 50


class NoTextError(ValueError):
    """The file is not a readable PDF or has no extractable text (scanned image)."""


def extract_text(pdf_bytes: bytes) -> str:
    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    except Exception as exc:
        raise NoTextError(f"could not open PDF: {exc}") from exc
    try:
        text = "\n".join(page.get_text() for page in doc)
    finally:
        doc.close()
    if len(text.strip()) < MIN_TEXT_CHARS:
        raise NoTextError(
            "no extractable text found — scanned-image resumes are not supported"
        )
    return text.strip()
