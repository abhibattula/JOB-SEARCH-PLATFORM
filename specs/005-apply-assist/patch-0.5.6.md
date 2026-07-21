# Patch 0.5.6: Fix Apply Assist not opening a browser window

**Reported**: 2026-07-21 — user installed v0.5.5, tried Apply Assist, and
no browser window opened. No error was shown either.

## Root cause

`engine/autofill/browser_setup.py`'s Chromium installer ran:

```python
subprocess.run([sys.executable, "-m", "playwright", "install", "chromium"], ...)
```

In a normal dev environment `sys.executable` is `python.exe`, so this
works. Inside the **installed, frozen app**, `sys.executable` is
`JobEngine.exe` itself — there is no Python interpreter behind it capable
of understanding `-m playwright install chromium`. The subprocess call
does not install anything; at best it's a no-op, at worst it tries to
relaunch the app. Chromium was therefore never actually being downloaded
in the shipped installer, so every "Start Apply Assist" click failed when
`_ensure_context()` tried to launch a browser that was never there.

Confirmed via `playwright/__main__.py` (the code Playwright's own `python
-m playwright` CLI entry point runs): it resolves
`playwright._impl._driver.compute_driver_executable()` — a real bundled
Node.js executable path, independent of `sys.executable` — and subprocesses
that directly. This is the correct, frozen-safe mechanism.

**Compounding bug**: this failure (and any other future failure) was
completely invisible to the user. `web/routes_autofill.py`'s `/queue`
route had no try/except around `browser_controller.start_queue(...)`, so
a real exception became a bare 500 with no user-facing detail. Worse,
`autofill.html`'s button click handlers used `await fetch(...)` and never
checked the response at all — success or failure looked identical: nothing
visibly happens.

## Fix

- `engine/autofill/browser_setup.py`: `_run_install()` now uses
  `compute_driver_executable()` + `get_driver_env()` directly, exactly
  mirroring Playwright's own `__main__.py`. Works identically in dev and
  frozen builds since it never touches `sys.executable`.
- `web/routes_autofill.py`: `/queue` and `/next` now catch exceptions from
  `browser_controller` and return `{"started": false, "error": "..."}`
  (200, not a bare 500) so the frontend can display the real problem.
- `web/templates/autofill.html`: both the "Enable Apply Assist" and "Start
  Apply Assist" buttons now check the fetch response and show a visible
  error banner on failure, instead of silently doing nothing. The Enable
  button also no longer relies on htmx swapping raw JSON into the DOM as
  HTML (a separate, related bug — it would have briefly shown literal
  `{"started": true}` text where the button was).

## Verification

TDD: `tests/test_browser_setup.py` gained a regression test asserting the
install subprocess command's first two arguments come from
`compute_driver_executable()` and that `sys.executable` never appears in
it — written first, watched fail against the old code (`AttributeError`,
since `compute_driver_executable` didn't exist as a module attribute yet),
then passed after the fix. `tests/test_routes_autofill.py` gained a test
for the error-surfacing behavior. Full suite: 271 passed.

**Live, end-to-end, in the actual frozen build** (not just unit tests,
since this bug specifically only manifests in frozen mode where
`sys.executable != python.exe`):
1. Rebuilt the installer with the fix.
2. Launched the real frozen exe in an isolated data directory.
3. Clicked through the exact reported flow via the real API: triggered
   Chromium setup, polled until `chromium_installed: true` (confirmed the
   real `chrome.exe` binary landed on disk), started a queue against a
   real job.
4. **Confirmed a real, visible Chromium window opened** (`Get-Process`
   showed `chrome.exe` with `MainWindowTitle: "example.com - Google Chrome
   for Testing"`, navigated to the queued job's URL) — this is the exact
   symptom the user reported, now fixed and independently verified against
   the actual shipped artifact, not assumed from unit tests alone.

## Ship

Tagged v0.5.6.
