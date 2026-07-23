"""007-T011: engine/resume_extract.py — LLM extraction of structured
resume sections, schema-validated with the matcher's bounded-retry idiom.

matcher._chat is always mocked: these tests are deterministic and
offline; the user-review step in the UI is the real quality gate.
"""
import json

import pytest

from engine import resume_extract
from engine.resume_extract import ResumeSections


VALID_PAYLOAD = {
    "experience": [
        {
            "title": "Firmware Intern",
            "organization": "Acme Robotics",
            "start": "2025-05",
            "end": "2025-08",
            "bullets": ["Wrote STM32 drivers", "Cut boot time 40%"],
        }
    ],
    "education": [
        {
            "degree": "B.S. Computer Engineering",
            "institution": "State University",
            "start": "2022-08",
            "end": "2026-05",
            "details": "GPA 3.8",
        }
    ],
    "projects": [
        {
            "name": "RISC-V core",
            "description": "5-stage pipelined core in SystemVerilog",
            "bullets": ["Passed rv32i compliance suite"],
        }
    ],
    "skills": ["python", "verilog", "i2c"],
}


class TestSchema:
    def test_valid_payload_roundtrips(self):
        sections = ResumeSections.model_validate(VALID_PAYLOAD)
        assert sections.experience[0].title == "Firmware Intern"
        assert sections.skills == ["python", "verilog", "i2c"]

    def test_partial_payload_is_valid(self):
        """Partial extraction is valid by design — missing lists default
        empty (spec edge case: show what extracted, forms for the rest)."""
        sections = ResumeSections.model_validate({"skills": ["python"]})
        assert sections.experience == []
        assert sections.education == []
        assert sections.projects == []

    def test_empty_entries_are_dropped(self):
        """Entries with no non-empty field are noise, not data."""
        sections = ResumeSections.model_validate(
            {
                "experience": [
                    {"title": "", "organization": "", "start": "", "end": "", "bullets": []},
                    {"title": "Real Job", "organization": "Acme", "start": "", "end": "", "bullets": []},
                ]
            }
        )
        assert len(sections.experience) == 1
        assert sections.experience[0].title == "Real Job"


class TestExtract:
    def test_extracts_via_chat_dispatcher(self, monkeypatch):
        from engine import matcher

        monkeypatch.setattr(matcher, "_chat", lambda messages, **kw: json.dumps(VALID_PAYLOAD))
        monkeypatch.setattr(matcher, "scoring_tier", lambda: "cloud")
        result = resume_extract.extract("resume text here")
        assert result is not None
        assert result.experience[0].organization == "Acme Robotics"

    def test_no_tier_returns_none(self, monkeypatch):
        from engine import matcher

        monkeypatch.setattr(matcher, "scoring_tier", lambda: "basic")
        monkeypatch.setattr(
            matcher, "_chat",
            lambda messages, **kw: (_ for _ in ()).throw(AssertionError("must not call")),
        )
        assert resume_extract.extract("resume text") is None

    def test_malformed_output_retries_once_then_none(self, monkeypatch):
        from engine import matcher

        calls = []

        def bad_chat(messages, **kw):
            calls.append(1)
            return "not json at all"

        monkeypatch.setattr(matcher, "_chat", bad_chat)
        monkeypatch.setattr(matcher, "scoring_tier", lambda: "cloud")
        assert resume_extract.extract("resume text") is None
        assert len(calls) == 2  # bounded retry, then give up — never raise

    def test_fenced_json_is_accepted(self, monkeypatch):
        from engine import matcher

        fenced = "```json\n" + json.dumps(VALID_PAYLOAD) + "\n```"
        monkeypatch.setattr(matcher, "_chat", lambda messages, **kw: fenced)
        monkeypatch.setattr(matcher, "scoring_tier", lambda: "cloud")
        result = resume_extract.extract("resume text")
        assert result is not None and result.skills == ["python", "verilog", "i2c"]


class TestContactAndTitles008:
    """008 US4 (T036): contact/target-title extraction + the pattern-based
    fallback that works with no AI at all (FR-022/FR-023)."""

    def test_schema_accepts_contact_and_target_titles(self):
        sections = resume_extract.ResumeSections.model_validate({
            "skills": ["verilog"],
            "contact": {
                "first_name": "Abhinav", "last_name": "Battula",
                "email": "abhi@example.com", "phone": "(555) 123-4567",
                "linkedin_url": "https://linkedin.com/in/abhinav",
                "portfolio_url": "https://github.com/abhi",
                "location": "Austin, TX",
            },
            "target_titles": ["Design Verification Engineer", "FPGA Engineer"],
        })
        assert sections.contact.email == "abhi@example.com"
        assert sections.target_titles[0] == "Design Verification Engineer"

    def test_target_titles_capped_at_five(self):
        sections = resume_extract.ResumeSections.model_validate(
            {"target_titles": [f"Title {i}" for i in range(9)]}
        )
        assert len(sections.target_titles) == 5

    def test_regex_fallback_extracts_email_phone_links(self):
        text = (
            "Abhinav Battula\n"
            "abhibattula2001@gmail.com | (512) 555-0100 | "
            "linkedin.com/in/abhinav-b | github.com/abhibattula\n"
            "Austin, TX\n\nEXPERIENCE\nDid engineering things.\n"
        )
        contact = resume_extract.extract_contact(text)
        assert contact.email == "abhibattula2001@gmail.com"
        assert "512" in contact.phone
        assert contact.linkedin_url == "https://linkedin.com/in/abhinav-b"
        assert contact.portfolio_url == "https://github.com/abhibattula"

    def test_regex_fallback_never_fabricates(self):
        contact = resume_extract.extract_contact("A resume with no contact block.")
        assert contact.email == ""
        assert contact.phone == ""
        assert contact.linkedin_url == ""
        assert contact.portfolio_url == ""

    def test_llm_prompt_requests_contact_block(self):
        assert "contact" in resume_extract._SYSTEM
        assert "target_titles" in resume_extract._SYSTEM


class TestChunkedLocalExtraction009:
    """009 US3 (T017): the local tier processes long resumes in bounded
    parts (root cause B2: a 24k-char single-shot prompt deterministically
    overflowed n_ctx=4096 and extraction failed silently 100% of the time)."""

    def test_split_chunks_respects_blank_line_boundaries(self):
        paragraphs = [f"SECTION {i}\n" + ("line of resume text. " * 40)
                      for i in range(10)]
        text = "\n\n".join(paragraphs)
        chunks = resume_extract._split_chunks(text, target=2000)
        assert len(chunks) > 1
        assert all(len(c) <= 3500 for c in chunks)  # near target, never huge
        # nothing lost, order preserved, splits only at blank lines
        assert "\n\n".join(chunks).replace("\n\n", "\n").replace("\n", " ") \
            .replace("  ", " ").strip() != ""
        joined = "".join(chunks)
        for i in range(10):
            assert f"SECTION {i}" in joined

    def test_split_never_cuts_mid_line(self):
        text = "\n\n".join("A" * 900 for _ in range(8))
        for chunk in resume_extract._split_chunks(text, target=2000):
            for line in chunk.splitlines():
                assert line == "" or set(line) == {"A"}
                assert len(line) in (0, 900)  # lines survive intact

    def test_merge_concatenates_ordered_and_dedupes(self):
        part1 = resume_extract.ResumeSections(
            experience=[{"title": "Intern", "organization": "Acme"}],
            skills=["Python", "Verilog"],
            target_titles=["FPGA Engineer"],
            contact={"email": "a@x.com"},
        )
        part2 = resume_extract.ResumeSections(
            experience=[{"title": "RA", "organization": "Uni"}],
            education=[{"degree": "BS CE", "institution": "UT"}],
            skills=["python", "SystemVerilog"],  # 'python' dupes casefolded
            target_titles=["FPGA Engineer", "DV Engineer"],
            contact={"email": "ignored@later.com", "phone": "(512) 555-0100"},
        )
        merged = resume_extract._merge([part1, part2])
        assert [e.title for e in merged.experience] == ["Intern", "RA"]
        assert merged.education[0].degree == "BS CE"
        assert merged.skills == ["Python", "Verilog", "SystemVerilog"]
        assert merged.target_titles == ["FPGA Engineer", "DV Engineer"]
        # contact: first non-empty value per field wins
        assert merged.contact.email == "a@x.com"
        assert merged.contact.phone == "(512) 555-0100"

    def test_merge_of_nothing_is_none(self):
        assert resume_extract._merge([]) is None

    def test_local_tier_uses_chunks_and_bounded_prompts(self, monkeypatch):
        from engine import matcher

        sizes = []

        def fake_chat(messages, **kw):
            sizes.append(len(messages[-1]["content"]))
            return json.dumps({"skills": ["python"]})

        monkeypatch.setattr(matcher, "_chat", fake_chat)
        monkeypatch.setattr(matcher, "scoring_tier", lambda: "local")
        long_resume = "\n\n".join("Paragraph of resume text. " * 60
                                  for _ in range(20))  # ~30k chars
        result = resume_extract.extract(long_resume)
        assert result is not None
        assert len(sizes) > 1  # chunked, not single-shot
        assert all(size <= 6000 for size in sizes), max(sizes)

    def test_local_chunk_failure_degrades_partially(self, monkeypatch):
        from engine import matcher

        calls = {"n": 0}

        def flaky_chat(messages, **kw):
            calls["n"] += 1
            if "PART-TWO-MARKER" in messages[-1]["content"]:
                raise RuntimeError("model hiccup")
            return json.dumps({"skills": [f"skill{calls['n']}"]})

        monkeypatch.setattr(matcher, "_chat", flaky_chat)
        monkeypatch.setattr(matcher, "scoring_tier", lambda: "local")
        text = ("A" * 4000) + "\n\n" + ("PART-TWO-MARKER " * 300) + "\n\n" + ("B" * 4000)
        result = resume_extract.extract(text)
        assert result is not None  # the good chunks survived
        assert result.skills  # something extracted

    def test_cloud_tier_keeps_single_shot(self, monkeypatch):
        from engine import matcher

        calls = []

        def fake_chat(messages, **kw):
            calls.append(len(messages[-1]["content"]))
            return json.dumps({"skills": ["python"]})

        monkeypatch.setattr(matcher, "_chat", fake_chat)
        monkeypatch.setattr(matcher, "scoring_tier", lambda: "cloud")
        long_resume = "x" * 30000
        resume_extract.extract(long_resume)
        assert len(calls) == 1  # unchanged single-shot on cloud


class TestProgressCallback009:
    def test_on_progress_reports_chunk_counts(self, monkeypatch):
        from engine import matcher

        monkeypatch.setattr(
            matcher, "_chat", lambda messages, **kw: json.dumps({"skills": []})
        )
        monkeypatch.setattr(matcher, "scoring_tier", lambda: "local")
        progress = []
        long_resume = "\n\n".join("text " * 300 for _ in range(10))
        resume_extract.extract(long_resume, on_progress=lambda done, total: progress.append((done, total)))
        assert progress
        done, total = progress[-1]
        assert done == total and total >= 2
