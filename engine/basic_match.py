"""Deterministic local match scoring — works with no API key, offline.

A curated SWE/hardware skill dictionary is matched (word-boundary regexes)
against the resume and the job description; the score reflects how much of the
JD's demanded skill set the resume covers. Results carry method="basic" so the
UI can mark them (~NN) and the pipeline can upgrade them to full LLM analysis
once a key is added.
"""
from __future__ import annotations

import re

from .matcher import GapAction, MatchAnalysis

# canonical skill -> regex (case-insensitive). Patterns chosen to avoid prose
# false-positives (no bare "c"/"go"/"r").
_SKILLS: dict[str, str] = {
    # software
    "python": r"\bpython\b",
    "java": r"\bjava\b(?!script)",
    "c++": r"c\+\+",
    "embedded c": r"\bembedded[- ]c\b",
    "javascript": r"\bjavascript\b|\bnode(?:\.js)?\b",
    "typescript": r"\btypescript\b",
    "golang": r"\bgolang\b",
    "rust": r"\brust\b",
    "sql": r"\bsql\b|\bpostgres(?:ql)?\b|\bmysql\b|\bsqlite\b",
    "react": r"\breact\b",
    "flask/django": r"\bflask\b|\bdjango\b|\bfastapi\b",
    "aws": r"\baws\b|\bamazon web services\b",
    "docker": r"\bdocker\b",
    "kubernetes": r"\bkubernetes\b|\bk8s\b",
    "linux": r"\blinux\b",
    "git": r"\bgit\b(?!hub\b|lab\b)",
    "rest api": r"\brest(?:ful)?\s*apis?\b",
    "ci/cd": r"\bci/?cd\b|\bcontinuous integration\b",
    "machine learning": r"\bmachine learning\b|\bpytorch\b|\btensorflow\b",
    # hardware
    "verilog": r"\bverilog\b(?<!system[- ]verilog)",
    "systemverilog": r"\bsystem[- ]?verilog\b",
    "vhdl": r"\bvhdl\b",
    "uvm": r"\buvm\b",
    "fpga": r"\bfpga\b",
    "asic": r"\basic\b",
    "rtl": r"\brtl\b",
    "soc": r"\bsoc\b|\bsystem[- ]on[- ]chip\b",
    "risc-v": r"\brisc[- ]?v\b",
    "arm architecture": r"\barm\s+(?:architecture|cortex|processor)\b|\bcortex[- ]m\b",
    "microcontroller": r"\bmicrocontrollers?\b|\bmcu\b|\bstm32\b|\barduino\b|\besp32\b",
    "i2c": r"\bi2c\b|\bi²c\b",
    "spi": r"\bspi\b",
    "uart": r"\buart\b",
    "pcb design": r"\bpcb\b|\baltium\b|\bkicad\b",
    "cadence/synopsys": r"\bcadence\b|\bsynopsys\b|\bvivado\b|\bquartus\b",
    "timing analysis": r"\btiming analysis\b|\bsta\b|\bsetup and hold\b",
    "dft": r"\bdft\b|\bscan insertion\b",
    "matlab": r"\bmatlab\b|\bsimulink\b",
    "oscilloscope/lab": r"\boscilloscopes?\b|\blogic analyzers?\b|\bmultimeters?\b",
    "verification": r"\bdesign verification\b|\bfunctional verification\b|\btestbench(?:es)?\b",
}
_COMPILED = {name: re.compile(pattern, re.IGNORECASE) for name, pattern in _SKILLS.items()}

NEUTRAL_SCORE = 45.0


def extract_skills(text: str) -> set[str]:
    if not text:
        return set()
    return {name for name, pattern in _COMPILED.items() if pattern.search(text)}


def score(
    resume_text: str, title: str, description: str, extra_skills: set[str] | None = None
) -> MatchAnalysis:
    """`extra_skills` (006-E): the user's explicit Profile skills list, on
    top of what regex extraction finds in the raw resume text — a skill
    the user knows but phrased differently (or omitted) in their resume
    still counts, which matters most for no-cloud-key basic-tier users."""
    resume_skills = extract_skills(resume_text)
    if extra_skills:
        # Only accept names from the canonical dictionary — extra_skills
        # may contain arbitrary free-text the user typed in Profile.
        resume_skills |= {s.lower() for s in extra_skills if s.lower() in _SKILLS}
    jd_text = f"{title}\n{description}"
    jd_skills = extract_skills(jd_text)

    if not jd_skills:
        return MatchAnalysis(
            match_score=NEUTRAL_SCORE,
            matching_skills=sorted(resume_skills)[:8],
            missing_skills=[],
            gap_actions=[],
            reasoning="Basic match: the posting lists no recognizable technical "
            "skills, so this is a neutral estimate.",
        )

    matching = sorted(jd_skills & resume_skills)
    missing = sorted(jd_skills - resume_skills)
    coverage = len(matching) / len(jd_skills)
    title_bonus = 5.0 if any(_COMPILED[s].search(title) for s in matching) else 0.0
    value = min(95.0, round(15.0 + 75.0 * coverage + title_bonus, 0))

    gaps = [
        GapAction(
            action=f"Add concrete evidence of {skill} to your resume",
            impact="Explicitly requested in this job's description",
        )
        for skill in missing[:3]
    ]
    return MatchAnalysis(
        match_score=value,
        matching_skills=matching,
        missing_skills=missing,
        gap_actions=gaps,
        reasoning=f"Basic match: resume covers {len(matching)} of "
        f"{len(jd_skills)} skills the posting asks for.",
    )
