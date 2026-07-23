# Quickstart & Gates: The Copilot Release (010)

## Dev run

```powershell
.venv\Scripts\python -m uvicorn web.main:app --port 8000   # app
# Chrome → chrome://extensions → Developer mode → Load unpacked →
#   <repo>\extension   (dev) or <data_dir>\extension (installed app)
# Badge turns green within ~10s of both sides running.
```

Practice loop: Apply Assist → "Test Apply Assist" now opens the practice
application in YOUR Chrome when connected (fallback window otherwise);
the essay question exercises draft → flag → confirm → reuse.

## Test suites

```powershell
.venv\Scripts\python -m pytest -q                # default (fast) suite
.venv\Scripts\python -m pytest -m browser -q     # Playwright + REAL extension vs fixture pages
.venv\Scripts\python -m pytest -m slow -q        # offline gates (real local model, incl. qa draft gate)
```

## Live gate (release-blocking)

Scripted (headed Chrome, real extension, real postings — extends the 009
live-gate script): one live Greenhouse (greenhouse.io-hosted), Lever,
Ashby posting each — companion fills ≥ the same field counts as the
v0.9.0 assistant window on the same postings; posting-page guidance class
verified on a custom-domain posting.

Manual checklist (user's real logged-in Chrome):
1. Companion connects ≤10s; survives app restart + Chrome restart.
2. Queue a job → tab opens in your Chrome → fields fill ≤2 passes;
   typing is never overwritten; nothing ever clicked.
3. "Fill this page" on a posting found by browsing → same behavior;
   tracker linkage offered.
4. Essay question → grounded concise draft, flagged on-page + in app;
   confirm in app → answer bank; re-run → fills with no flag ≤5s.
5. Visa/sponsorship question → NO draft; confirm-gate flow unchanged.
6. Submit an application yourself → "Mark as applied?" appears; confirm →
   status advances + drafts auto-saved; decline → nothing changes.
7. Disconnect mid-job (quit app) → overlay stops, interrupted; relaunch →
   Resume works. Fallback: disable extension → queue runs in assistant
   window with mode clearly shown.
8. Every page in light + dark: coherent identity, no unstyled surface.

## Frozen build + smoke

```powershell
.venv\Scripts\python -m PyInstaller packaging\jobengine.spec --noconfirm
.venv\Scripts\python packaging\smoke_test.py dist\JobEngine\JobEngine.exe
```

Smoke additions: `extension/` assets present in the bundle & stamped into
the data dir with pairing.json; `/api/bridge/info` answers; `/companion`
serves; `/api/next-actions` answers; existing 009 assertions unchanged.

## Ship ritual

Full pytest ×2 + `-m browser` + slow gates → frozen build + smoke → live
gate → merge → mirror `001-ai-job-engine` → tag v1.0.0 → verify BOTH
installers on the Release page.
