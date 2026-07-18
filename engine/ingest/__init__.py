"""Source registry. Each source module exposes SOURCE_NAME and
fetch_jobs(entries) -> iterable[RawJob], where entries are its companies.yml
rows (empty for company-less sources like HN and jobspy)."""
from __future__ import annotations

import importlib

SOURCE_ORDER = [
    "greenhouse", "lever", "ashby", "smartrecruiters", "workable",
    "workday", "hn", "jobspy",
]

_MODULES = {
    "greenhouse": "engine.ingest.greenhouse",
    "lever": "engine.ingest.lever",
    "ashby": "engine.ingest.ashby",
    "smartrecruiters": "engine.ingest.smartrecruiters",
    "workable": "engine.ingest.workable",
    "workday": "engine.ingest.workday",
    "hn": "engine.ingest.hn",
    "jobspy": "engine.ingest.jobspy_source",
}


def get_source(name: str):
    return importlib.import_module(_MODULES[name])
