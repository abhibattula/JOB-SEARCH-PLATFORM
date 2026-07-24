"""USCIS H-1B Data Hub + DOL LCA disclosure loaders and the fuzzy join from
job-board company names to sponsorship records.

Both datasets are free public government downloads (see quickstart.md). The
DOL disclosure files are very large, so only the needed columns are read and
rows are filtered to engineering SOC codes (15-xxxx computer, 17-2xxx
engineering) before titles are stored.
"""
from __future__ import annotations

import logging
import re
from pathlib import Path

from rapidfuzz import fuzz, process

from . import db

log = logging.getLogger(__name__)

FUZZY_THRESHOLD = 90
MAX_TITLES_PER_EMPLOYER = 20


def score_from_approvals(approvals: int) -> str:
    from .filters import HIGH_APPROVALS_THRESHOLD

    if approvals >= HIGH_APPROVALS_THRESHOLD:
        return "HIGH"
    if approvals >= 1:
        return "MEDIUM"
    return "UNKNOWN"


# --- sponsorship intelligence (007, FR-011/012/013) ---------------------------

# A grade is assigned only with enough evidence (clarified floor): small
# samples produce noise, and a fabricated-looking grade is worse than
# UNKNOWN (SC-003).
GRADE_MIN_PETITIONS = 10

# Grade formula weights (research.md §9) — explainable on the evidence
# panel, tunable as constants without schema changes.
_W_APPROVAL_RATE = 55.0
_W_VOLUME = 25.0
_W_ENG_LCA = 10.0
_W_WAGE = 10.0

_WAGE_LEVEL_ORDER = {"I": 1, "II": 2, "III": 3, "IV": 4}


def grade(approvals: int, denials: int, has_eng_lca: bool = False,
          wage_level: str | None = None) -> str | None:
    """Local A–F sponsor grade from public evidence, or None (UNKNOWN)
    below the petition floor. Deterministic and unit-tested."""
    import math

    approvals = max(0, int(approvals or 0))
    denials = max(0, int(denials or 0))
    total = approvals + denials
    if total < GRADE_MIN_PETITIONS:
        return None
    approval_rate = approvals / total
    volume = min(1.0, math.log10(approvals + 1) / 3.0)  # 1000+ approvals = full credit
    wage_rank = _WAGE_LEVEL_ORDER.get(wage_level or "", 0)
    wage_credit = 1.0 if wage_rank >= 3 else (0.5 if wage_rank == 2 else 0.0)
    score = (
        _W_APPROVAL_RATE * approval_rate
        + _W_VOLUME * volume
        + _W_ENG_LCA * (1.0 if has_eng_lca else 0.0)
        + _W_WAGE * wage_credit
    )
    if score >= 85:
        return "A"
    if score >= 70:
        return "B"
    if score >= 55:
        return "C"
    if score >= 40:
        return "D"
    return "F"


# Word-boundary patterns (the filters.py idiom — "Universal Instruments"
# must never match "university", "Collegium" never "college").
_CAP_EXEMPT_RE = re.compile(
    r"\buniversit(y|ies)\b|\bcolleges?\b|\binstitute\b|\bhospitals?\b"
    r"|\bmedical center\b|\bhealth system\b|\bacademy\b"
    r"|\bresearch (institute|center|centre|foundation|laborator(y|ies))\b"
    r"|\bnational\b[\w\s]{0,40}\blaborator(y|ies)\b|\bschool of\b",
    re.IGNORECASE,
)


def cap_exempt(company_name: str) -> bool:
    """Heuristic: universities / nonprofit research / hospital systems are
    H-1B cap-exempt — they skip the lottery and can sponsor year-round.
    Presented as 'likely' in the UI (estimate language, FR-012)."""
    return bool(_CAP_EXEMPT_RE.search(company_name or ""))


_LOTTERY_HINTS = {
    "IV": "Level IV wages — strongest odds under the wage-weighted lottery (estimate)",
    "III": "Level III wages — favorable odds under the wage-weighted lottery (estimate)",
    "II": "Level II wages — average odds under the wage-weighted lottery (estimate)",
    "I": "Level I wages — weakest odds under the wage-weighted lottery (estimate)",
}


def lottery_hint(wage_level: str | None) -> str | None:
    """FR-013: the 2026 wage-weighted selection rule favors higher wage
    levels; the hint is derived from the company's median LCA level and
    always labeled an estimate. None without wage data — never invented."""
    return _LOTTERY_HINTS.get(wage_level or "")


def match_employer(company_name: str, employers: dict) -> tuple[str, int] | None:
    """Match a job-board company name to (display_name, approvals) or None.

    `employers` maps normalized name -> (display_name, approvals) tuples or
    {"display_name": ..., "approvals": ...} dicts.
    """

    def unpack(value):
        if isinstance(value, dict):
            return value.get("display_name"), value.get("approvals", 0)
        return value[0], value[1]

    normalized = db.normalize_company(company_name)
    if normalized in employers:
        return unpack(employers[normalized])
    hit = process.extractOne(
        normalized, employers.keys(), scorer=fuzz.ratio, score_cutoff=FUZZY_THRESHOLD
    )
    if hit is not None:
        return unpack(employers[hit[0]])
    # Legal names often carry a generic industry tail the board name lacks
    # ("Palantir" vs "PALANTIR TECHNOLOGIES INC"): compare with those stripped.
    stripped = _strip_generic(normalized)
    if stripped:
        for key, value in employers.items():
            if _strip_generic(key) == stripped:
                return unpack(value)
    return None


_GENERIC_TAIL = {
    "technologies", "technology", "labs", "laboratories", "systems",
    "solutions", "software", "holdings", "group", "international",
    "global", "usa", "us", "na", "pbc",
}


def _strip_generic(normalized: str) -> str:
    words = normalized.split()
    while len(words) > 1 and words[-1] in _GENERIC_TAIL:
        words.pop()
    return " ".join(words)


def store_employers(employers: dict) -> None:
    """Persist normalized -> {display_name, approvals, lca_titles} records."""
    db.store_h1b_employers(employers)


def grade_company(name: str, employers: dict | None = None) -> dict:
    """Grade a single company on demand from the public H-1B records.

    The reusable core of the per-company grading loop (feature 012): a job-board
    company name → `{sponsor_grade, cap_exempt, approvals, has_sponsor_data,
    denials, wage_level, lca_titles}`. `apply_to_companies` (batch) and
    `discovery.score_page` (on demand for a browsed posting) both call this so
    the two paths can never diverge. `employers` may be passed to avoid reloading
    the in-memory dict per call; None loads it. Never fabricates a grade below
    the petition floor (grade() returns None → "unknown"); the cap-exempt flag is
    independent evidence and always applies.
    """
    is_cap_exempt = cap_exempt(name)
    if employers is None:
        employers = db.load_h1b_employers()
    hit = match_employer(name, employers) if employers else None
    if hit is None:
        return {
            "sponsor_grade": None, "cap_exempt": is_cap_exempt, "approvals": 0,
            "has_sponsor_data": False, "denials": 0, "wage_level": None,
            "lca_titles": None,
        }
    display, approvals = hit
    record = employers.get(db.normalize_company(display)) or {}
    record = record if isinstance(record, dict) else {}
    denials = int(record.get("denials") or 0)
    wage_level = record.get("wage_level_median")
    lca_titles = record.get("lca_titles")
    return {
        "sponsor_grade": grade(approvals, denials,
                               has_eng_lca=bool(lca_titles), wage_level=wage_level),
        "cap_exempt": is_cap_exempt,
        "approvals": int(approvals or 0),
        "has_sponsor_data": True,
        "denials": denials,
        "wage_level": wage_level,
        "wage_offered": record.get("wage_offered_median"),
        "lca_titles": lca_titles,
    }


def apply_to_companies() -> int:
    """Match every not-yet-checked company against stored employer records.

    Returns the number of companies that matched. All examined companies are
    marked checked so repeated passes stay cheap; companies discovered by
    later refreshes are picked up on the next call.
    """
    employers = db.load_h1b_employers()
    if not employers:
        return 0
    matched = 0
    for company in db.get_unchecked_companies():
        graded = grade_company(company["name"], employers)
        if graded["has_sponsor_data"]:
            db.set_company_sponsorship(
                company["id"],
                approvals=graded["approvals"],
                sponsor_score=score_from_approvals(graded["approvals"]),
                lca_titles=graded["lca_titles"],
                denials=graded["denials"],
                wage_level_median=graded["wage_level"],
                wage_offered_median=graded["wage_offered"],
                cap_exempt=graded["cap_exempt"],
                sponsor_grade=graded["sponsor_grade"],
            )
            matched += 1
        else:
            # No USCIS record: never a fabricated grade (SC-003) — but the
            # cap-exempt flag is independent evidence and still applies.
            db.set_company_sponsorship(
                company["id"], approvals=0, sponsor_score="UNKNOWN",
                cap_exempt=graded["cap_exempt"],
            )
    return matched


# --- file loaders ------------------------------------------------------------


def _find_column(columns, *needles) -> str | None:
    for column in columns:
        lowered = str(column).lower()
        if all(needle in lowered for needle in needles):
            return column
    return None


def load_uscis_dir(directory: str | Path) -> tuple[dict, int]:
    """Aggregate approvals per employer from USCIS Data Hub CSVs."""
    import pandas as pd

    employers: dict[str, dict] = {}
    files = sorted(Path(directory).glob("*.csv")) if Path(directory).exists() else []
    for path in files:
        try:
            frame = pd.read_csv(path, dtype=str, on_bad_lines="skip", encoding_errors="replace")
        except Exception:
            log.warning("could not read %s", path, exc_info=True)
            continue
        name_col = _find_column(frame.columns, "employer")
        if name_col is None:
            log.warning("%s: no employer column, skipped", path.name)
            continue
        approval_cols = [
            c for c in frame.columns if "approval" in str(c).lower()
        ]
        # 007 (FR-010): denial columns feed the sponsor grade's approval
        # rate; files without them behave exactly as before.
        denial_cols = [c for c in frame.columns if "denial" in str(c).lower()]
        for col in approval_cols + denial_cols:
            frame[col] = (
                pd.to_numeric(
                    frame[col].astype(str).str.replace(",", ""), errors="coerce"
                ).fillna(0)
            )
        for _, row in frame.iterrows():
            name = str(row[name_col] or "").strip()
            if not name or name.lower() == "nan":
                continue
            normalized = db.normalize_company(name)
            if not normalized:
                continue
            approvals = int(sum(row[c] for c in approval_cols)) if approval_cols else 0
            denials = int(sum(row[c] for c in denial_cols)) if denial_cols else 0
            entry = employers.setdefault(
                normalized, {"display_name": name, "approvals": 0, "denials": 0}
            )
            entry["approvals"] += approvals
            entry["denials"] = entry.get("denials", 0) + denials
    return employers, len(files)


def load_dol_dir(directory: str | Path, employers: dict) -> int:
    """Attach engineering job titles from DOL LCA disclosure files."""
    import pandas as pd

    files = []
    if Path(directory).exists():
        files = sorted(
            [*Path(directory).glob("*.xlsx"), *Path(directory).glob("*.csv")]
        )
    for path in files:
        try:
            if path.suffix == ".csv":
                frame = pd.read_csv(path, dtype=str, on_bad_lines="skip", encoding_errors="replace")
            else:
                frame = pd.read_excel(path, dtype=str)
        except Exception:
            log.warning("could not read %s", path, exc_info=True)
            continue
        name_col = _find_column(frame.columns, "employer", "name")
        title_col = _find_column(frame.columns, "job", "title")
        soc_col = _find_column(frame.columns, "soc", "code")
        # 007 (FR-010): prevailing-wage level + offered wage feed the grade
        # and lottery hint; files without those columns behave as before.
        level_col = _find_column(frame.columns, "wage", "level")
        offered_col = _find_column(frame.columns, "wage", "from")
        if not name_col or not title_col:
            log.warning("%s: missing employer/title columns, skipped", path.name)
            continue
        columns = [name_col, title_col] + [
            c for c in (soc_col, level_col, offered_col) if c
        ]
        subset = frame[columns].dropna(subset=[name_col, title_col])
        if soc_col:
            soc = subset[soc_col].astype(str)
            subset = subset[soc.str.startswith("15-") | soc.str.startswith("17-2")]
        wage_samples: dict[str, dict[str, list]] = {}
        for _, row in subset.iterrows():
            normalized = db.normalize_company(str(row[name_col]))
            entry = employers.get(normalized)
            if entry is None:
                continue
            titles = entry.setdefault("lca_titles", [])
            title = str(row[title_col]).strip()
            if title and title not in titles and len(titles) < MAX_TITLES_PER_EMPLOYER:
                titles.append(title)
            samples = wage_samples.setdefault(normalized, {"levels": [], "offered": []})
            if level_col:
                rank = _WAGE_LEVEL_ORDER.get(str(row[level_col]).strip().upper())
                if rank:
                    samples["levels"].append(rank)
            if offered_col:
                try:
                    offered = float(str(row[offered_col]).replace(",", "").replace("$", ""))
                    if offered > 0:
                        samples["offered"].append(offered)
                except ValueError:
                    pass
        import statistics

        rank_to_level = {rank: level for level, rank in _WAGE_LEVEL_ORDER.items()}
        for normalized, samples in wage_samples.items():
            entry = employers[normalized]
            if samples["levels"]:
                median_rank = round(statistics.median(samples["levels"]))
                entry["wage_level_median"] = rank_to_level.get(median_rank)
            if samples["offered"]:
                entry["wage_offered_median"] = float(statistics.median(samples["offered"]))
    return len(files)


def load_all(uscis_dir: str | Path = "data/uscis", dol_dir: str | Path = "data/dol") -> dict:
    employers, uscis_files = load_uscis_dir(uscis_dir)
    dol_files = load_dol_dir(dol_dir, employers)
    store_employers(employers)
    matched = apply_to_companies()
    return {
        "employers": len(employers),
        "uscis_files": uscis_files,
        "dol_files": dol_files,
        "companies_matched": matched,
    }
