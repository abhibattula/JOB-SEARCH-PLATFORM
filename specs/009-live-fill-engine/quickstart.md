# Quickstart — verifying Feature 009 (The Live Fill Engine)

## Dev loop

```powershell
.venv\Scripts\python -m pytest -q            # fast suite (browser tests excluded by default)
.venv\Scripts\python -m pytest -m browser -q # real-browser fixture suite (headless Edge/Chrome)
.venv\Scripts\python desktop.py              # real shell
```

## Ten-second proof (do this first)

Apply Assist → **Test Apply Assist** → watch the practice application
fill your real data live: identity fields, resume file attached,
work-authorization dropdown matched, the delayed section fills ~2s after
it renders, the iframe section fills too. Activity feed counts match.

## Live gate (release-blocking)

For ONE real posting each on Greenhouse, Lever, Ashby, Indeed/Workable:

1. Queue it. Browser lands on the FORM page for Lever/Ashby (URL ends
   `/apply` / `/application`); Greenhouse inline; others on the posting
   with guidance shown.
2. Fields fill within ~2 ticks (≈4s) of the form appearing. Where a form
   needs the site's Apply button — click it yourself; the revealed fields
   fill.
3. Multi-page: click the site's own Next — the next page's fields fill.
4. Type into a field while the watcher runs — it never overwrites you.
5. Confirm-answer flow fills the paused field. Close the window → resume
   works. Jobs #2/#3 behave identically to #1.
6. Nothing is ever clicked by the app. Batch summary is accurate.

## Profile import walkthrough (offline tier)

Settings: leave "Prefer offline model" ON. Profile → upload a multi-page
resume: page responds instantly → progress banner advances
(contact → skills → sections part i/N) → review screen lists every field
current-vs-resume with sane defaults (or the compact "everything already
matches" confirmation) → Apply selected → toast + visibly updated
profile + refreshed search terms. Re-run via "Import from resume". Kill
the network first: identical behavior (offline). Flip the toggle off →
extraction runs via Groq, much faster, same review screen.

## Frozen build + smoke

```powershell
.venv\Scripts\python -m PyInstaller packaging\jobengine.spec --noconfirm
.venv\Scripts\python packaging\smoke_test.py dist\JobEngine\JobEngine.exe
# smoke now also asserts: status.activity present, import status idle,
# /practice/apply serves
```

Ship: full suite ×2 + `-m browser` suite green → docs → version 0.9.0 →
frozen smoke → live gate → merge → mirror `001-ai-job-engine` → tag
v0.9.0 → both installers verified on the Release page.
