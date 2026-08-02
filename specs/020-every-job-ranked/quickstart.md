# Quickstart: verifying Every Job Ranked (feature 020)

Run in order. §3 is the one that proves the headline claim, and it runs
against the applicant's real database rather than a fixture.

---

## 1. Automated gates

```powershell
.venv\Scripts\python.exe -m pytest -q                 # full unit battery, twice
.venv\Scripts\python.exe -m pytest -m browser -q      # real-browser suite
.venv\Scripts\python.exe -m pytest -q tests/test_secret_hygiene.py
```

Baseline before this feature: **1622 unit** (5m03s) and **90 browser**
(18m27s), both green. The count must go up, never down.

---

## 2. Frozen smoke

```powershell
.venv\Scripts\python.exe -m PyInstaller packaging/jobengine.spec --noconfirm
.venv\Scripts\python.exe packaging/smoke_test.py
```

The smoke asserts against the HTTP surface only — it must never import
`engine` (the v1.9.0 lesson that failed a tag twice).

---

## 3. The headline check — real data, real backlog

**Back up first**, then measure against a copy:

```powershell
Copy-Item data\jobs.db data\backup\jobs-pre-2.0.0.db
```

Baseline on the applicant's database (2026-08-01):

| measure | before |
|---|---|
| total jobs | 22,145 |
| eligible | 937 |
| eligible **scored** | 310 (33%) |
| eligible **unscored** | **627** |
| embedded | 600 |

```powershell
$env:JOBS_DB_PATH = "data\jobs.db"
.venv\Scripts\python.exe -c @'
import time
from engine import db, pipeline
db.init_db()
t0 = time.time()
pipeline.run_refresh("verify", force=True)
print("refresh returned in %.1fs" % (time.time() - t0))
'@
```

**Pass conditions**

- `refresh returned in` **under 60 seconds** (SC-003) — it previously held
  open for 2 h 47 m.
- Eligible unscored afterwards is **0** (SC-001):

```powershell
.venv\Scripts\python.exe -c @'
import sqlite3
c = sqlite3.connect("data/jobs.db")
e = "delisted=0 AND is_entry_level=1 AND sponsorship!='EXCLUDED'"
print("eligible        ", c.execute(f"SELECT COUNT(*) FROM jobs WHERE {e}").fetchone()[0])
print("still unscored  ", c.execute(f"SELECT COUNT(*) FROM jobs WHERE {e} AND match_score IS NULL").fetchone()[0])
for m, n in c.execute(f"SELECT json_extract(match_json,'$.method'), COUNT(*) FROM jobs WHERE {e} AND match_score IS NOT NULL GROUP BY 1"):
    print("  method %-6s %d" % (m, n))
'@
```

- The refresh run is **finished**, so a second refresh is accepted under the
  ordinary cooldown rather than refused as `running`.

**Ranking must not need the model** (SC-002, FR-002): repeat the refresh with
inference forced to fail and confirm coverage is still 100%.

```powershell
$env:JOBS_AI_TIMEOUT_CHAT = "0.001"
```

---

## 4. Background assessment

With the app running:

1. Open the feed. A progress indicator shows **AI-scoring _n_ / 40**.
2. Reload the feed repeatedly for a minute. The count moves forward and
   **never restarts or doubles** — one pass exists (SC-005, FR-009).
3. Watch a few jobs flip from `~` to `•` in place, score and badge together.
4. Close the app mid-pass and reopen it. Assessment resumes; at most one job's
   work was lost (FR-010).

---

## 5. Applying beats ranking (SC-006, FR-013)

The regression this feature is most likely to cause — verify it deliberately.

1. Start a refresh so a background pass is running.
2. Immediately start Apply Assist on a real application with a free-text
   question that needs a drafted answer.
3. **Pass**: the draft arrives in its usual time. The assessment pass shows
   `paused_for_session` and stops consuming the model until the session ends.
4. **Fail**: the draft takes minutes or times out — the pass is not standing
   down.

---

## 6. Rich-text cover letters (SC-007)

On a real Greenhouse or Lever application whose cover letter is a rich-text
editor:

1. The companion counts the box as a field — the "fields seen" number includes
   it.
2. With an answer available, the text lands in the editor and **stays there
   after clicking elsewhere** (proves the page registered a real input event,
   not a silent DOM write).
3. With no answer, the box appears as a needs-you item naming the question —
   never silently blank.
4. While it is empty and required, the escort **does not advance** past it.

---

## 7. Companion idle cost (SC-008)

Open the benchmark added in this feature against a large form-free page and
compare against the recorded pre-change baseline. Required: **at least a 50%
reduction** in periodic inspection cost, with the browser suite still green.

Then confirm no detection was lost: open a job posting, let the page sit for a
minute so the poll has backed off, then trigger the in-page navigation to the
application form. The companion must pick the form up without a noticeable
delay (FR-021).

---

## 8. Feed listing index (SC-009)

```powershell
.venv\Scripts\python.exe -c @'
import sqlite3
c = sqlite3.connect("data/jobs.db")
q = ("SELECT id FROM jobs WHERE delisted=0 AND is_entry_level=1 "
     "AND sponsorship!='EXCLUDED' ORDER BY COALESCE(posted_date, first_seen) DESC LIMIT 50")
for r in c.execute("EXPLAIN QUERY PLAN " + q):
    print(r[3])
'@
```

**Pass**: no `USE TEMP B-TREE FOR ORDER BY`. Before: 67.9 ms with that line
present.

---

## 9. iCIMS advance (FR-023)

On a real iCIMS application: the step advances by its own recognised control,
one click per rendered step, and still stops at the final Submit. Confirm in
the activity ledger that the click was recorded and that no final-class control
was ever clicked.

---

## 10. Automation line unchanged (FR-024)

Non-negotiable, re-verified every release:

- A real Workday application escorts to Review and **stops** — Submit is never
  clicked.
- A LinkedIn Easy Apply fills and clicks **nothing**.
- Create account is filled but never pressed.
- No CAPTCHA is ever interacted with.

This includes **T076 carried over from 019**, still outstanding: install, press
↻ on the companion card at `chrome://extensions`, save a Workday login, and run
one real Workday application end to end.

---

## 11. Ship

Tag `v2.0.0`, then verify **both** installers from the release body by magic
bytes and SHA-256 — Windows `4d5a`, macOS `7801`. A green build is not
evidence; the digests are.
