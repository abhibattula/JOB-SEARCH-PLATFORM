# Quickstart & Gates: The Coverage Release (011)

## Dev run

```powershell
.venv\Scripts\python -m uvicorn web.main:app --port 8000
# Chrome → chrome://extensions → reload the Job Engine Companion (unpacked
# code is cached until reload). Dot green within ~30s.
```

Practice loop: Apply Assist → "Test Apply Assist" — the practice page now
includes a **custom dropdown** so you can watch it fill (open → pick → set)
in your own browser.

## Test suites

```powershell
.venv\Scripts\python -m pytest -q                # fast suite (incl. click_guard matrix, widget field_core, adapters, static guards)
.venv\Scripts\python -m pytest -m browser -q     # real extension vs fixture pages (fills combo/typeahead/Workday-style; submit-never-clicked)
.venv\Scripts\python -m pytest -m slow -q        # offline model gates
```

## Live gate (release-blocking)

Manual, in the user's own logged-in Chrome:
1. A **custom dropdown** (work-auth / EEO) fills to the saved value; one with
   no matching option is left, reported "fill manually".
2. A **Workday** application (real posting, e.g. an NVIDIA/AMD role): the
   identity/contact fields + at least one custom combo + one location/school
   typeahead fill; you click Workday's own **Next** — the following page
   fills; the app never clicks Next/Submit.
3. A **submit button styled like an option** (or a real Submit near the
   options) is never clicked by the app.
4. Fallback: disable the companion → the same custom dropdown fills in the
   assistant window (parity).
5. All 010/009 behaviors intact (native fields, file upload, AI drafts,
   pause-for-review, saved-login, activity feed).

Scripted (extends 010's headed-Chrome live gate): real Greenhouse/Lever/
Ashby postings still fill ≥ their prior field counts, now including any
custom dropdowns on them.

## Frozen build + smoke

```powershell
.venv\Scripts\python -m PyInstaller packaging\jobengine.spec --noconfirm
.venv\Scripts\python packaging\smoke_test.py dist\JobEngine\JobEngine.exe
```
Smoke additions: `extension/content/click_guard.js` present in the bundle &
stamped into the data dir; bridge/info reports 1.1.0.

## Ship ritual

Full pytest ×2 + `-m browser` + `-m slow` → frozen build + smoke → live gate
→ merge → mirror `main:001-ai-job-engine` → tag v1.1.0 → verify BOTH
installers on the Release page.
