"""Entry-level classification and sponsorship signal extraction.

Decision order for entry-level (title exclusions always win):
  1. seniority marker in title        -> not entry-level
  2. entry marker in title            -> entry-level
  3. hardware-family title            -> entry-level unless the description
                                         demands 3+ years
  4. entry marker in description      -> entry-level
  5. otherwise                        -> not entry-level (generic titles are
                                         default-out to keep the feed precise)
"""
from __future__ import annotations

import re

_EXCLUDE_TITLE = [
    r"\bsenior\b", r"\bsr\.?\s", r"\bstaff\b", r"\bprincipal\b", r"\blead\b",
    r"\bmanager\b", r"\bdirector\b", r"\barchitect\b", r"\bhead of\b",
    r"\bchief\b", r"\b(ii|iii|iv|v)\b", r"\b[3-9]\+\s*years",
]
_INCLUDE_TITLE = [
    r"new grad", r"university grad", r"college grad", r"\bncg\b",
    r"entry[- ]level", r"\bjunior\b", r"\bassociate\b", r"early[- ]career",
    r"rotation program", r"\bgraduate\b", r"engineer\s*[(]?\s*(i|1)\b",
    r"0\s*[-–]\s*2\s*years",
]
_HARDWARE_TITLE = [
    r"hardware engineer", r"\bembedded\b", r"\bfirmware\b", r"\bfpga\b",
    r"\basic\b", r"\bverification\b", r"\bvalidation\b", r"\bsilicon\b",
    r"\brtl\b", r"\bdft\b", r"physical design",
]
_DESC_ENTRY = [
    r"0\s*[-–]\s*2\s*years", r"recent graduate", r"new grad",
    r"entry[- ]level", r"no prior experience",
]
_DESC_SENIOR = [
    r"\b(?:[3-9]|\d{2})\+\s*years", r"at least\s+(?:[3-9]|\d{2})\s+years",
    r"minimum\s+(?:of\s+)?(?:[3-9]|\d{2})\s+years",
]
# The feed targets SWE/hardware roles: entry markers alone must not qualify
# sales/ops/recruiting titles ("New Grad Account Executive").
_ENGINEERING_ROLE = [
    r"engineer", r"developer", r"software", r"hardware", r"firmware",
    r"\bembedded\b", r"\bfpga\b", r"\basic\b", r"\bsilicon\b", r"\brtl\b",
    r"verification", r"validation", r"\bsde\b", r"\bswe\b", r"programmer",
    r"\bdft\b",
]


def _any(patterns: list[str], text: str) -> bool:
    return any(re.search(pattern, text) for pattern in patterns)


def classify_entry_level(title: str, description: str = "") -> bool:
    t = (title or "").lower()
    if _any(_EXCLUDE_TITLE, t):
        return False
    if not _any(_ENGINEERING_ROLE, t):
        return False
    if _any(_INCLUDE_TITLE, t):
        return True
    d = (description or "").lower()[:4000]
    if _any(_HARDWARE_TITLE, t):
        return not _any(_DESC_SENIOR, d)
    return _any(_DESC_ENTRY, d)


# --- sponsorship -------------------------------------------------------------

# Ineligibility wording. The user needs sponsorship: clearance, citizens-only,
# and ITAR/export-control "U.S. person" requirements (citizen or green card —
# OPT does not qualify) all mean the role is not applyable.
_NEGATIVE = [re.compile(p) for p in (
    r"unable to sponsor", r"will not sponsor", r"cannot sponsor",
    r"not able to sponsor", r"without sponsorship", r"citizens only",
    r"citizenship required", r"not require sponsorship",
    r"no visa sponsorship", r"sponsorship is not available",
    r"not offer sponsorship", r"not provide sponsorship",
    r"security clearance",
    r"\bitar\b", r"\bu\.?s\.?\s+persons?\b", r"export control",
    r"export regulations", r"\b(?:active|secret|top secret)\s+clearance",
    r"ts\s*/\s*sci", r"must be a u\.?s\.?\s+citizen",
    r"green card holders?\s+(?:only|will be considered)",
)]
_POSITIVE = ["visa sponsorship", "will sponsor", "sponsorship available", "h-1b", "h1b"]
_POSITIVE_CASED = [r"\bOPT\b", r"\bCPT\b"]  # uppercase acronyms only

HIGH_APPROVALS_THRESHOLD = 25


def scan_sponsorship(text: str) -> tuple[int, str | None]:
    """Return (flag, phrase): 1 positive, 0 silent, -1 ineligible."""
    lowered = (text or "").lower()
    for pattern in _NEGATIVE:
        match = pattern.search(lowered)
        if match:
            return -1, match.group(0)
    for phrase in _POSITIVE:
        if phrase in lowered:
            return 1, phrase
    for pattern in _POSITIVE_CASED:
        match = re.search(pattern, text or "")
        if match:
            return 1, match.group(0)
    return 0, None


def rate_sponsorship(h1b_approvals: int, jd_flag: int) -> tuple[str, dict]:
    """Combine company history with JD wording; negative wording always wins."""
    evidence = {"h1b_approvals": h1b_approvals or 0}
    if jd_flag == -1:
        return "EXCLUDED", evidence
    if jd_flag == 1 or (h1b_approvals or 0) >= HIGH_APPROVALS_THRESHOLD:
        return "HIGH", evidence
    if (h1b_approvals or 0) >= 1:
        return "MEDIUM", evidence
    return "UNKNOWN", evidence
