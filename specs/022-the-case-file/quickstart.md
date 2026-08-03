# Quickstart — 022 The Case File

## Run it

```powershell
.venv\Scripts\python.exe -m uvicorn web.main:app --reload --port 8000
# then open http://127.0.0.1:8000
```

Toggle theme from Settings, or force it:

```powershell
.venv\Scripts\python.exe -c "from engine import settings; settings.set('THEME','dark')"
.venv\Scripts\python.exe -c "from engine import settings; settings.set('THEME','light')"
.venv\Scripts\python.exe -c "from engine import settings; settings.set('THEME','')"   # follow the OS
```

Force a density:

```powershell
.venv\Scripts\python.exe -c "from engine import settings; settings.set('FEED_DENSITY','comfortable')"
```

## See all three stamps at once

The stamp is a pure function of `match_json.method`, so seed one job per value:

```powershell
.venv\Scripts\python.exe - <<'PY'
import json
from engine import db
db.init_db()
rows = [r["id"] for r in db.recent_jobs(limit=3)]
for job_id, method in zip(rows, ("basic", "local", "llm")):
    db.set_match(job_id, {"basic": 55, "local": 68, "llm": 81}[method],
                 json.dumps({"match_score": {"basic": 55, "local": 68,
                                             "llm": 81}[method],
                             "method": method, "matching_skills": [],
                             "missing_skills": [], "reasoning": "seeded"}))
print("seeded", rows)
PY
```

A fourth state — "not scored yet" — is any job with no match row, which the feed
already has plenty of.

## Verify

```powershell
# the new gate: the audit, as a test
.venv\Scripts\python.exe -m pytest tests/test_design_system.py -v

# full unit battery (run twice; the second run catches order dependence)
.venv\Scripts\python.exe -m pytest -q -m "not browser"
.venv\Scripts\python.exe -m pytest -q -m "not browser"

# real browser — panel theme, stamp, drag
.venv\Scripts\python.exe -m pytest -q -m browser

# secrets never reach a surface
.venv\Scripts\python.exe -m pytest -q tests/test_secret_hygiene.py
```

### The feed must go quiet

```powershell
# with the app running and the feed open, watch the partial endpoint
.venv\Scripts\python.exe - <<'PY'
import time, urllib.request
url = "http://127.0.0.1:8000/partials/feed?window=14d&sort=score"
for i in range(6):
    with urllib.request.urlopen(url) as r:
        print(f"{i}: {r.status}")     # first 200, then 204 while unchanged
    time.sleep(2)
PY
```

Expected: one `200`, then `204` for as long as nothing changes. Any `200` while
the data is static means the fingerprint is hashing something invisible.

### Ship gates (in order — the first one is not optional)

```powershell
# 1. version consistency FIRST. v2.1.0 nearly shipped broken because
#    packaging/windows.iss still said 2.0.0 and only the workflow caught it.
.venv\Scripts\python.exe packaging/check_version.py

# 2. frozen build smoke
.venv\Scripts\python.exe packaging/smoke_test.py

# 3. browser suite on BOTH platforms — macOS caught two bugs Windows passed
#    in 020 and forced the tag to be cut twice.
```

## The approval gate

**Phase 1 stops here.** Before any of the other eight screens are touched, the
applicant receives screenshots of the Feed in light and dark, showing the stamp
at all three provenance levels, and approves or redirects (SC-011).

**No tag, no release, no push of a version until they say go.**

## Visual pass checklist

Walk each screen in light and dark:

Feed · job detail · Profile · Settings · Apply Assist · Companion ·
Diagnostics · Analytics · Learned answers

Then: the panel on a real application page, and both generated PDFs.

Look for the things a test cannot judge — whether the hierarchy reads, whether
the stamp is legible at `sm`, whether comfortable density is actually more
comfortable, and whether anything still looks like an unstyled fallback.
