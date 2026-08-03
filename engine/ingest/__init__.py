"""Source registry. Each source module exposes SOURCE_NAME and
fetch_jobs(entries) -> iterable[RawJob], where entries are its companies.yml
rows (empty for company-less sources like HN and jobspy)."""
from __future__ import annotations

import importlib

SOURCE_ORDER = [
    "greenhouse", "lever", "ashby", "simplify", "smartrecruiters", "workable",
    # 021 (FR-033): five more keyless, official JSON boards on the same
    # shape. They reach the employer's own careers page, so the apply URL
    # is the genuine one rather than an aggregator's copy.
    "recruitee", "teamtailor", "personio", "breezy", "jazzhr",
    "workday", "hn", "jobspy",
]

_MODULES = {
    "greenhouse": "engine.ingest.greenhouse",
    "lever": "engine.ingest.lever",
    "ashby": "engine.ingest.ashby",
    "simplify": "engine.ingest.simplify",
    "smartrecruiters": "engine.ingest.smartrecruiters",
    "workable": "engine.ingest.workable",
    "recruitee": "engine.ingest.recruitee",
    "teamtailor": "engine.ingest.teamtailor",
    "personio": "engine.ingest.personio",
    "breezy": "engine.ingest.breezy",
    "jazzhr": "engine.ingest.jazzhr",
    "workday": "engine.ingest.workday",
    "hn": "engine.ingest.hn",
    "jobspy": "engine.ingest.jobspy_source",
}


def get_source(name: str):
    return importlib.import_module(_MODULES[name])
