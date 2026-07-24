"""009 T026: the offline-tier gate — the REAL bundled model must extract
sections from a realistic multi-page resume via the chunked path. This is
the case that failed silently 100% of the time in v0.8.0 (context
overflow). Minutes of real inference: run with `pytest -m slow`."""
import pytest

from engine import local_llm, qa, resume_extract

pytestmark = pytest.mark.slow

RESUME = """Abhinav Battula
abhibattula2001@gmail.com | (512) 555-0100 | linkedin.com/in/abhinav-b | github.com/abhibattula
Austin, TX

OBJECTIVE
New-grad computer engineer seeking design verification and FPGA roles.

EXPERIENCE

Hardware Engineering Intern — Aurora Semiconductors, Austin TX (May 2025 - Aug 2025)
- Built UVM testbenches for a PCIe Gen5 controller block, raising functional coverage from 71% to 94%.
- Automated regression triage with Python, cutting debug turnaround from days to hours.
- Presented coverage-closure methodology to a 12-engineer verification team.

Undergraduate Research Assistant — UT Austin ECE (Jan 2024 - May 2025)
- Implemented a RISC-V vector accelerator prototype on a Xilinx UltraScale+ FPGA.
- Profiled memory-bandwidth bottlenecks; redesigned the AXI interconnect for a 1.8x speedup.
- Co-authored a workshop paper on energy-efficient vector load/store units.

Teaching Assistant, Digital Logic Design — UT Austin (Aug 2023 - Dec 2023)
- Led weekly lab sections of 30 students covering Verilog, FSMs, and timing analysis.

EDUCATION
BS Computer Engineering, University of Texas at Austin, 2021 - 2025. GPA 3.8.
Coursework: Computer Architecture, VLSI Design, Embedded Systems, Operating Systems.

PROJECTS

Out-of-Order RISC-V Core (2025)
- Designed a 2-wide OoO core in SystemVerilog with Tomasulo scheduling and a 92% IPC of ideal.
- Verified with a constrained-random instruction generator and riscv-dv comparison flows.

FPGA Retro Console (2024)
- Recreated a NES-class console on an Artix-7; wrote the PPU pipeline and APU mixer in Verilog.
- Achieved cycle-accurate timing against hardware traces.

SKILLS
SystemVerilog, Verilog, UVM, Python, C/C++, RISC-V, FPGA (Xilinx/Intel), AXI/PCIe, Git, Linux,
Synopsys VCS, Verdi, Vivado, Quartus, Formal verification basics.
""" * 4  # ~7,200 chars — exceeds CHUNK_TARGET_CHARS so the chunked path really runs


class TestOfflineExtractionGate:
    def test_real_local_model_extracts_sections_chunked(self, tmp_db, monkeypatch):
        if not local_llm.available():
            pytest.skip("bundled local model not present")
        monkeypatch.delenv("LLM_API_KEY", raising=False)
        progress = []
        result = resume_extract.extract(
            RESUME, on_progress=lambda done, total: progress.append((done, total))
        )
        assert result is not None, "offline extraction returned nothing (v0.8.0 regression)"
        assert len(result.experience) >= 1
        assert result.skills, "no skills extracted"
        assert progress and progress[-1][0] == progress[-1][1] >= 2  # really chunked


class TestOfflineDraftGate:
    """010 US2: the offline model must produce a grounded, concise draft for
    an open-ended question — and refuse (None) when there is nothing to
    ground in, never fabricating."""

    PROFILE = {
        "resume_text": (
            "Abhinav Battula — Computer Engineer. Hardware Engineering Intern "
            "at Aurora Semiconductors: built UVM testbenches for a PCIe Gen5 "
            "controller, raised functional coverage from 71% to 94%. Skills: "
            "SystemVerilog, UVM, Python, RISC-V, FPGA."
        ),
        "first_name": "Abhinav",
    }
    JOB = {"title": "Design Verification Engineer", "company": "Figma",
           "description": "Own UVM-based verification for our custom silicon."}

    def test_real_local_model_drafts_grounded_answer(self, tmp_db, monkeypatch):
        if not local_llm.available():
            pytest.skip("bundled local model not present")
        monkeypatch.delenv("LLM_API_KEY", raising=False)
        draft = qa.draft("Why do you want to work here?", "free_text_unknown",
                         self.PROFILE, self.JOB)
        assert draft, "offline drafting returned nothing"
        assert len(draft) <= 900  # concise, not a wall of text
        # grounded in the applicant's real facts, not generic filler
        lowered = draft.lower()
        assert any(term in lowered for term in
                   ("uvm", "verification", "systemverilog", "aurora", "pcie"))

    def test_refuses_without_grounding(self, tmp_db, monkeypatch):
        if not local_llm.available():
            pytest.skip("bundled local model not present")
        monkeypatch.delenv("LLM_API_KEY", raising=False)
        # empty resume/profile → nothing to ground in → None (never fabricate)
        assert qa.draft("Why us?", "free_text_unknown",
                        {"resume_text": ""}, self.JOB) is None
