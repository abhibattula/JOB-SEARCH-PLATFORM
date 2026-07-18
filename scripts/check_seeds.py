"""Validate companies.yml seed entries against their live board endpoints.

Usage: python scripts/check_seeds.py [--prune]

Reports each entry as OK (with job count) or FAIL (with reason). With --prune,
rewrites companies.yml keeping only OK entries (a backup is written first).
Wrong slugs fail silently as zero jobs in the app, so run this after editing.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import httpx
import yaml

ROOT = Path(__file__).resolve().parents[1]
SEEDS = ROOT / "companies.yml"

HEADERS = {"User-Agent": "PersonalJobEngine/1.0 (personal use)"}


def check_entry(client: httpx.Client, entry: dict) -> tuple[bool, str]:
    ats = entry.get("ats")
    try:
        if ats == "greenhouse":
            r = client.get(
                f"https://boards-api.greenhouse.io/v1/boards/{entry['slug']}/jobs"
            )
            if r.status_code != 200:
                return False, f"HTTP {r.status_code}"
            return True, f"{len(r.json().get('jobs', []))} jobs"
        if ats == "lever":
            r = client.get(
                f"https://api.lever.co/v0/postings/{entry['slug']}?mode=json"
            )
            if r.status_code != 200:
                return False, f"HTTP {r.status_code}"
            data = r.json()
            if not isinstance(data, list):
                return False, "unexpected payload"
            return True, f"{len(data)} jobs"
        if ats == "ashby":
            r = client.get(
                f"https://api.ashbyhq.com/posting-api/job-board/{entry['slug']}"
            )
            if r.status_code != 200:
                return False, f"HTTP {r.status_code}"
            return True, f"{len(r.json().get('jobs', []))} jobs"
        if ats == "workday":
            tenant = entry["host"].split(".")[0]
            url = f"https://{entry['host']}/wday/cxs/{tenant}/{entry['site']}/jobs"
            r = client.post(
                url,
                json={"appliedFacets": {}, "limit": 1, "offset": 0, "searchText": ""},
            )
            if r.status_code != 200:
                return False, f"HTTP {r.status_code}"
            return True, f"{r.json().get('total', '?')} total"
        return False, f"unknown ats {ats!r}"
    except Exception as exc:  # noqa: BLE001 - report any failure per entry
        return False, f"{type(exc).__name__}: {exc}"


def main() -> int:
    prune = "--prune" in sys.argv
    doc = yaml.safe_load(SEEDS.read_text(encoding="utf-8"))
    entries = doc["companies"]
    ok_entries, failures = [], []
    with httpx.Client(timeout=20, headers=HEADERS, follow_redirects=True) as client:
        for entry in entries:
            good, detail = check_entry(client, entry)
            mark = "OK  " if good else "FAIL"
            print(f"{mark} {entry.get('ats', '?'):10} {entry['name']:22} {detail}")
            (ok_entries if good else failures).append(entry)
            time.sleep(0.6)
    print(f"\n{len(ok_entries)} OK, {len(failures)} failed of {len(entries)}")
    if prune and failures:
        SEEDS.with_suffix(".yml.bak").write_text(
            SEEDS.read_text(encoding="utf-8"), encoding="utf-8"
        )
        doc["companies"] = ok_entries
        SEEDS.write_text(
            yaml.safe_dump(doc, sort_keys=False, allow_unicode=True), encoding="utf-8"
        )
        print(f"Pruned {len(failures)} entries (backup: companies.yml.bak)")
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
