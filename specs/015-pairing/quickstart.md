# Quickstart — verifying Feature 015 (The Pairing Release)

Dev-machine walkthrough proving each user story. Automated equivalents live in
the test suite (see research.md R12); this is the human pass.

## 0. Setup

```powershell
python desktop.py     # or: python app.py  (dev data dir = .\data)
```

## 1. US1 — stability

1. **Hammer (automated is authoritative):** `pytest tests/test_inference.py -q`
   — asserts serialized execution, timeout, and saturation behavior with a
   stub model.
2. **Status stays live during drafting:** start Apply Assist on the practice
   application, get a pending question, watch the panel — the question shows
   "drafting a suggestion…" immediately and the status keeps refreshing every
   ~3 s (never a frozen panel), the suggestion appearing in place when ready.
3. **Unclean-exit banner:** while the app runs, kill the process
   (`taskkill /F /IM python.exe` or end JobEngine.exe in Task Manager);
   relaunch → one-time banner "the app closed unexpectedly last time" linking
   diagnostics; dismiss → gone on next load.
4. *(Spike GO only)*: with `JOBS_AI_SUBPROCESS=1`, kill the AI child process
   mid-draft → app stays up, the field reports needs-manual, the next AI
   request works, doctor notes the restart.

## 2. US2 — pairing, verified live

1. Open **Connect your browser** (`/companion`). With nothing installed, the
   wizard shows: app preparation ✓ (stamp status), companion — not detected,
   with instructions + copy-path.
2. Load the shown folder in **Chrome** (`chrome://extensions` → Developer mode
   → Load unpacked). Within ~30 s the wizard flips to
   **Connected — Chrome (companion v1.5.0)**. Repeat in **Edge** →
   "Connected — Edge".
3. **Popup truth:** close the app; click the companion toolbar icon → popup
   says the app isn't running and offers Retry; "Fill this page" explains
   instead of doing nothing. Relaunch the app → Retry connects.
4. **Stamp failure is loud:** simulate (test does it via fault injection;
   manual: make `<data_dir>/extension/pairing.json` read-only, relaunch) →
   banner on Apply Assist + connect pages naming the failure; doctor
   (`/api/companion/doctor`) shows `stamp.ok=false` + reason. Restore.
5. **Queue-start disclosure (D2):** with the companion connected, start a
   queue → status shows "Filling in your Chrome (companion…)". Disable the
   extension, start another queue → it proceeds AND shows the warning banner
   "Assistant window — <browser> (not signed in)" with a connect link.
6. **Doctor:** open Diagnostics → companion section shows the full chain
   green; with the extension loaded from a WRONG folder, rejects stay 0 and
   companion never connects (the wizard's troubleshooting covers it); with a
   STALE pairing (edit port), rejects.auth climbs and the popup explains.

## 3. US3 — browser intent

1. Settings shows **Preferred browser** = Chrome (default). With Windows'
   default set to Edge: the mismatch line appears ("Windows default: Edge ·
   Preference: Chrome") with the [Fix Windows default] button →
   ms-settings:defaultapps opens.
2. Open a job (`/api/open` path, e.g. the job-detail Apply button) → lands in
   **Chrome** even though the OS default is Edge. Set preference = Auto →
   lands in Edge (the OS default). Uninstalled-preference fallback: set
   preference to a browser not installed → opens in the OS default and the
   UI notes the substitution.
3. Start a queue with no companion → the assistant window launches
   **Chrome-first** (preference), Edge only as fallback.

## 4. US4 — rough edges

1. **Practice confirm:** run the practice application, answer the pending
   question → saves (200), session continues, the answer appears in Profile →
   Common Questions. (Regression: previously a server error.)
2. **Updater sims (automated):** `pytest tests/test_updates.py -q` — empty
   download rejected before hashing with a clear message; locked-file cleanup
   deferred to next launch; prune keeps ≤ newest previous installer.
3. Check `<data_dir>/updates/` after an update cycle: current + at most one
   older installer remain.

## 5. Gates before ship

```powershell
pytest -q                    # ×2 (full battery, twice)
pytest -m browser -q         # incl. NEW test_pairing_e2e (Edge AND Chrome)
pytest -m slow -q
python packaging\check_version.py v1.5.0
# frozen build + smoke (now also gates stamping):
pyinstaller packaging\jobengine.spec
python packaging\smoke_test.py "<ABSOLUTE path>\dist\JobEngine\JobEngine.exe"
```

Ship ritual: merge `015-pairing` → `main`, mirror `main:001-ai-job-engine`,
tag `v1.5.0`, verify BOTH installers (exe MZ / dmg 78 01 + SHA-256).
