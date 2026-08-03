# Quickstart — Feature 021 "The Real Application"

Manual verification, in the order a person would actually do it. Sections 1–3
are the evidence this feature was built from; 4–10 are the acceptance pass.

Run everything against the **installed** build, not the dev server, wherever a
step says "frozen".

---

## 1. Record the baseline (before any change)

```
.venv\Scripts\python.exe -m pytest -q
.venv\Scripts\python.exe -m pytest -m browser -q
```

Both must be green and their counts recorded in `baseline.txt`. Post-change
counts must **exceed** them, never fall below (v2.0.0: 1731 unit, 104 browser).

---

## 2. Capture the real page (Workstream A — gates B and C)

1. Open the Intel Workday application that produced Filled 5 · Needs you 149 ·
   Seen 156.
2. Start Apply Assist.
3. In the panel, press **Save page report**.
4. Open Diagnostics in the app; the report is listed. Download it.

**Check before going further:**

- The file contains **no value you typed**, no secret, and the `url_host` is a
  host with no path and no query string.
- `counts.seen` — is it really ~156 distinct fields in one scan, or fewer
  fields counted repeatedly? This answers R1's open question.
- `counts.sections` and how many `fields[]` entries resolved a
  `section_label` — this is the real coverage number for section detection.

Build `tests/fixtures/ats_pages/workday_my_experience.html` from what the
report describes.

---

## 3. Recheck the same page after B and C

Re-run steps 2.1–2.3 and compare `counts` against 5 / 149 / 156. Record both
numbers in `baseline.txt`. SC-002 requires needs-you to fall by at least 60%.

---

## 4. One row per question, named, grouped

On the captured application:

- No question appears twice **within one section**.
- No row is blank — every visible row names its question.
- Rows are grouped under section headings ("Work Experience 2", "Education 1").
- Two different sections that both ask "Start date" still show **two** rows.
- Advance three wizard steps: step one's fields are no longer listed as
  outstanding.
- "Show me" on a collapsed row reaches each element behind it in turn.

---

## 5. Work history and education fill themselves

Profile → confirm the parsed employment and education entries; correct one
deliberately.

- The second work-history block fills from the **second** employment entry.
- With two stored entries and three blocks on the form, the third block is
  left for you and is **not** filled from entry one or two.
- An education entry with no GPA leaves "Overall Result (GPA)" for you —
  it never borrows a number from anywhere.
- The correction you made in the profile is the value that gets typed.

---

## 6. The app learns what you type

1. Answer, by hand, a field the app left for you.
2. Wait for the next scan.
3. App → **Learned answers**: the question and your answer are listed, with the
   application they came from.
4. Open a different application asking the same question → it is offered.
5. Edit one, delete one, then press **Forget everything learned** — all
   observed answers go, and nothing the app already knew from your profile or
   your confirmed answers is affected.

**The one that matters most:** fill a password, an SSN, a date of birth and a
self-identification question by hand. **None** of them may appear on the
Learned answers page, in any log, or in a page report.

---

## 7. Tailoring completes, or says why

- Press **Tailor for this job**. Text appears progressively rather than a
  spinner that vanishes.
- Start a background AI pass, then immediately press Tailor: it is served
  next, and completes inside its budget.
- Force a failure (stop the AI runtime mid-request): a plain message appears.
  Never a silent no-op.

---

## 8. The AI tier is honest and fast

- Settings states plainly what leaves the machine for each choice.
- Save a free Groq key → applicant-initiated work is served by the cloud tier,
  and a tailoring request completes at least 10x faster than the recorded
  on-device time.
- Disconnect the network → the same request falls back to the on-device model
  with no action from you.
- Remove the key entirely → everything still works offline exactly as before.
- A refresh's bulk scoring still runs on-device and does **not** consume the
  cloud tier's daily budget.

---

## 9. The panel goes where you put it

- Drag it by its header; it follows and stays.
- Reload → it restores to where you left it.
- Resize the window small → it clamps fully into view, never off-screen.
- On a page with aggressive CSS, its placement still wins.
- **Reset position** returns it to the default corner.

---

## 10. The automation line is unchanged

The whole point of every release since 019. Frozen build:

- Escort a real Workday application to the review step — **Submit is never
  pressed**.
- A CAPTCHA is never interacted with.
- Nothing is ever clicked on LinkedIn.
- "Create account" and any payment control stay yours.

This is 019's still-outstanding **T076** and it carries forward until it is
performed on a frozen build.

---

## 11. Ship gates

```
# FIRST — the version gate. It compares the tag, packaging/windows.iss and
# engine.APP_VERSION, and it exists because they drifted silently once
# before. Running it locally turns a failed CI round-trip into two seconds.
set GITHUB_REF_NAME=v2.1.0 && .venv\Scripts\python.exe packaging\check_version.py

.venv\Scripts\python.exe -m pytest -q                    # twice
.venv\Scripts\python.exe -m pytest -m browser -q         # ALONE, not in background
.venv\Scripts\python.exe -m pytest -q tests/test_secret_hygiene.py
.venv\Scripts\python.exe packaging\smoke_test.py         # against the frozen build
```

Then the browser suite **on macOS as well**. v2.0.0's tag had to be cut twice
because macOS caught two real bugs Windows passed; running it on one platform
is not a pass.

Tag `v2.1.0`, then verify **both** installers by magic bytes and SHA-256
against the release body before announcing anything.
