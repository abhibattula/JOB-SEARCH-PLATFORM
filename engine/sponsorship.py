"""USCIS H-1B Data Hub + DOL LCA disclosure loaders and the fuzzy join from
job-board company names to sponsorship records.

Both datasets are free public government downloads (see quickstart.md). The
DOL disclosure files are very large, so only the needed columns are read and
rows are filtered to engineering SOC codes (15-xxxx computer, 17-2xxx
engineering) before titles are stored.
"""
from __future__ import annotations

import logging
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
        hit = match_employer(company["name"], employers)
        if hit is not None:
            display, approvals = hit
            record = employers.get(db.normalize_company(display)) or {}
            db.set_company_sponsorship(
                company["id"],
                approvals=approvals,
                sponsor_score=score_from_approvals(approvals),
                lca_titles=(record.get("lca_titles") if isinstance(record, dict) else None),
            )
            matched += 1
        else:
            db.set_company_sponsorship(company["id"], approvals=0, sponsor_score="UNKNOWN")
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
        for col in approval_cols:
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
            entry = employers.setdefault(
                normalized, {"display_name": name, "approvals": 0}
            )
            entry["approvals"] += approvals
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
        if not name_col or not title_col:
            log.warning("%s: missing employer/title columns, skipped", path.name)
            continue
        columns = [name_col, title_col] + ([soc_col] if soc_col else [])
        subset = frame[columns].dropna(subset=[name_col, title_col])
        if soc_col:
            soc = subset[soc_col].astype(str)
            subset = subset[soc.str.startswith("15-") | soc.str.startswith("17-2")]
        for _, row in subset.iterrows():
            normalized = db.normalize_company(str(row[name_col]))
            entry = employers.get(normalized)
            if entry is None:
                continue
            titles = entry.setdefault("lca_titles", [])
            title = str(row[title_col]).strip()
            if title and title not in titles and len(titles) < MAX_TITLES_PER_EMPLOYER:
                titles.append(title)
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
