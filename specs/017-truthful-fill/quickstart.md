# Quickstart: Feature 017 — The Truthful Fill

How to run the app, exercise each user story, and verify the feature end to
end. Commands assume the repository root on Windows (PowerShell); the Bash
equivalents are identical apart from path separators.

---

## Run

```powershell
python -m uvicorn web.main:app --reload --port 8765
```

Open `http://127.0.0.1:8765`. Pair the companion once from **Companion** if it
is not already connected (`chrome://extensions` → reload after any version
change, so the exact-version gate lifts).

## Test

```powershell
python -m pytest -q                          # full battery
python -m pytest -q -m "not browser and not slow"   # fast loop
python -m pytest -q tests/integration/test_pairing_e2e.py -m browser
python -m pytest -q tests/test_vocab.py tests/test_profile_answers.py tests/test_field_shape.py
```

Frozen build gate (run before shipping):

```powershell
python packaging/smoke_test.py
```

---

## Practice fixtures

The bundled fixtures reproduce the shapes that failed on the live Akuna form,
so none of this requires a real application:

| URL | Contains |
|---|---|
| `/practice/posting` | posting page with a hidden-until-Apply form, `?newtab=1` for the child-tab case |
| `/practice/apply` | the full field set — see below |

`/practice/apply` includes, added by this feature: a React-select dropdown
whose label is a 400-character acknowledgement and whose search input is nested
inside the control; a binding-exclusivity variant of that acknowledgement; a
pronoun **checkbox group**; a "please list **their** name" field; a "how your
name is pronounced **phonetically**" field; a work-authorization **expiry text**
field; a gender select worded `Man / Woman / Prefer not to say`; a location
typeahead; a lone-`Name` variant; and a résumé file input that reports the
attached file's name and size.

The fixture self-reports its DOM state to `/practice/fixture-state` every
second — this is the only observation channel for extension-opened tabs, which
Playwright cannot reach.

---

## Verifying each user story

### US1 — Nothing false, nothing runaway, always stoppable

1. Profile → leave "Have you applied here before" style library answers blank.
2. Start Apply Assist on `/practice/apply`.
3. **Expect**: questions with no grounding are **empty and highlighted**, not
   invented. The activity log shows `needs you`, reason `never_generated` or
   `cannot_answer`.
4. **Expect**: each question appears **once** in the drafts list. Watch
   `Diagnostics` — generation count per question never exceeds 2.
5. Scroll the status panel: **Stop / Done / Re-scan stay pinned at the top**
   regardless of field count, and the view does not jump on the 3 s refresh.
6. Profile → **Reset learned answers** → confirm the counts, then verify the
   fabricated answers no longer appear on a second run.

### US2 — Right answer in the right field

On `/practice/apply` after a fill:

- the acknowledgement dropdown contains **no text at all** and is highlighted;
- the "phonetically" field does **not** contain the phone number;
- the "list their name" field does **not** contain the applicant's name;
- the work-auth **expiry** field is empty or holds a date — never `Yes`;
- the pronoun checkbox group is treated as **one** question in the activity
  log, not five;
- with both `First name` and `Last name` present, a lone `Name` field receives
  the **first** name.

### US3 — Profile depth

1. Profile → fill Address, Work authorization detail, Experience facts, Links.
2. Re-run the fill.
3. **Expect**: `Country`, `City`, `State`, graduation month/year, GPA and the
   work-auth detail questions all fill from the profile with **no model call**
   (the activity log shows no `drafting…` entry for them).
4. Clear one field, re-run: that field is now empty and highlighted — not
   guessed.

### US4 — Say it the way the form says it

1. Profile → set `selfid_gender = Man`, `selfid_orientation = Straight`.
2. Re-run against the fixture whose select offers `Man / Woman / Prefer not to
   say` and another offering `Male / Female`.
3. **Expect**: both select the equivalent option.
4. Set `Prefer not to say` and re-run against a form offering "Decline to
   self-identify" — **expect** that option selected.
5. **Expect**: the binding-exclusivity acknowledgement is never answered, and
   its full text appears in the panel.

### US5 — Attach the real résumé

1. On a job you have **not** tailored, run a fill.
2. **Expect**: the fixture reports the attached filename and size matching your
   uploaded résumé — not an app-generated PDF.
3. Run `Tailor for this job`, then re-run: **expect** the tailored document.
4. Rename the résumé file on disk and re-run: **expect** nothing attached and
   the field reported as needing you — never a placeholder or an HTML body.

### US6 — See and act on the drafts

1. During a fill, click the floating badge → the panel opens.
2. **Expect**: every question with its full answer text, a **Copy** button, and
   an **Insert** button; needs-you entries scroll to their field when selected.
3. Type an answer into a refused question's input.
4. **Expect**: the field fills immediately, and on the next application the
   same question fills without asking (SC-010).

### US7 — Apply with Apply Assist

1. Open any job in the app → click **Apply with Apply Assist**.
2. **Expect**: a session starts for that job without visiting the queue page.
3. On a job posting in Chrome, use the badge's **Apply with Apply Assist**:
   the posting is saved and a session starts on that tab.

---

## Ship checklist

1. Full battery twice, plus the `browser` and `slow` markers.
2. `python packaging/smoke_test.py` on the frozen build, with
   `JOBS_AI_SUBPROCESS` at its default (on).
3. Docs updated: `USER_MANUAL.md`, `README.md`, `WHATS_NEW["1.7.0"]`.
4. Tag `v1.7.0`, wait for the **Release installers** workflow, then verify
   **both** artifacts — magic bytes (`4d5a` for the exe, `7801` for the dmg)
   and the SHA-256 in the release body against GitHub's stored digest.
5. If either job fails, delete the release and tag
   (`gh release delete v1.7.0 --cleanup-tag`), fix, and re-tag — never ship a
   partial release.
