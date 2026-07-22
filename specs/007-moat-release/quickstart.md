# Quickstart: The Moat Release (007)

End-to-end walkthrough proving all four pillars against the running app.
Prereqs: dev venv, `python -m pytest -q` green, app running
(`.\run.bat` or `uvicorn web.main:app`).

## 1. Resume builder + tailored PDF (US2)

1. Profile → upload your resume PDF. With a Groq key or the bundled local
   model available, the Resume builder section populates with extracted
   experience/education/projects/skills. Without any AI tier, the same
   forms appear empty for manual entry.
2. Edit one experience bullet, save — reload and confirm it persisted.
3. Re-upload the same PDF → confirm the keep-vs-re-extract prompt appears
   (your edit is not silently lost).
4. Open a scored job → Tailor → "Download tailored resume (PDF)" — open
   the file: selectable text, single column, your edited bullet present,
   job-tailored summary at top. Download the cover-letter PDF.

## 2. Apply Assist depth (US1)

5. Save 2+ jobs (at least one Greenhouse/Lever posting with a resume
   upload field and multi-page flow). Apply Assist → Start.
6. Mission-control panel shows the queue (titles + companies, not ids),
   "1 of N", and the current job highlighted.
7. On the opened application: identity fields filled, resume file
   attached (tailored variant if one exists and the toggle is on),
   dropdowns (e.g., work authorization) selected by option text.
8. Fill report lists every filled field; if a saved login was used, the
   password row reads "Password ••• (filled)".
9. Click the site's own Next → page 2 fields fill automatically; the app
   never clicks any button.
10. Close the browser window mid-queue → panel shows interrupted state →
    Resume queue → browser reopens on the same job.
11. Finish/skip through the queue → batch summary shows per-job outcomes.

## 3. Sponsorship intelligence (US3)

12. Ensure `data/uscis/*.csv` (and optionally `data/dol/*.xlsx`) exist →
    `python cli.py load-sponsorship` → refresh feed.
13. Feed rows show A–F grades where evidence ≥ 10 petitions; a university
    employer shows the cap-exempt badge; companies below the floor still
    show UNKNOWN.
14. Job detail → evidence panel: approvals, denials, approval rate, wage
    level, lottery hint, grade reasons.
15. Toggle "Strong sponsors only" → feed narrows to grade ≥ B or
    cap-exempt.

## 4. Redesign (US4)

16. Every page renders in the light "datasheet" theme; Settings → switch
    to dark "scope" → every page renders correctly; restart the app —
    choice persists.
17. Nav shows grouped sections with the current page active.
18. Mark a job saved → toast within 1s. Open a notes editor on Applied,
    wait 10s → editor and text survive the poll.
19. Applied → board view: stage columns with counts; drag a card to
    Interview (and move one via ◀/▶ buttons) → toast + persisted stage.
20. Fresh data dir (`JOBS_DATA_DIR`/`JOBS_DB_PATH` overrides): onboarding
    checklist appears with live completion state; completes/disappears as
    steps finish.

## 5. Regression + frozen

21. `python -m pytest -q` — full suite green, twice.
22. Frozen build: `pyinstaller packaging/jobengine.spec` +
    `python packaging/smoke_test.py <exe>` — includes the new
    `/api/diagnostics/pdf-selftest` check.
23. Both CI installers green on the release tag; artifacts present on the
    GitHub Release.
