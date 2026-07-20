# Releasing installers

Installers are built automatically by GitHub Actions — you never build the Mac
one by hand (that needs a Mac; the CI runner is one).

## One-time setup

1. Create a GitHub repository and push this project (Abhinav's steps):
   ```powershell
   winget install GitHub.cli        # once
   gh auth login                    # once, browser flow
   gh repo create job-engine --private --source . --push
   ```
2. That push alone starts the **CI** workflow (tests on every push).

## Cutting a release

1. Bump `APP_VERSION` in `engine/__init__.py`, and the version in
   `packaging/windows.iss` (`MyAppVersion`) and `packaging/jobengine.spec`
   (`CFBundleShortVersionString`). Commit.
2. Tag and push:
   ```powershell
   git tag v0.3.0
   git push origin 001-ai-job-engine --tags
   ```
3. The **Release installers** workflow builds on `windows-latest` and
   `macos-latest` (tests run first on both) and attaches to the GitHub Release:
   - `JobEngine-Setup-<version>.exe` — Windows installer (Start-menu entry,
     optional desktop icon, uninstaller)
   - `JobEngine-<version>.dmg` — macOS disk image (drag "Job Engine.app" to
     Applications)
4. Share the Release page link. Done.

## What users need to know (put in the release notes)

- **Windows**: SmartScreen will warn because the app is unsigned — click
  **More info → Run anyway** the first time.
- **macOS**: Gatekeeper blocks unsigned apps on double-click — **right-click →
  Open → Open** the first time (only needed once).
- The app stores all data locally: `%LOCALAPPDATA%\JobEngine` on Windows,
  `~/Library/Application Support/JobEngine` on macOS.
- First run: upload a resume — match scores work immediately via the bundled
  offline AI model, no key needed. Pasting a free Groq API key on the
  Settings page upgrades scoring further; everything else works without it.
- The installer is noticeably larger (~1GB+) than pre-005 releases because
  it bundles that AI model. Apply Assist's browser-engine download
  (~150-280MB) only happens the first time that specific feature is used.
- Apply Assist never auto-submits or auto-logs-in — the human always
  performs the final action; see the one-time in-app notice shown before
  first use for the Terms-of-Service caveat.

## Local Windows-only build (optional, for testing)

```powershell
.venv\Scripts\python.exe -m pip install pyinstaller
.venv\Scripts\python.exe -m pip install -r requirements.txt --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cpu
.venv\Scripts\python.exe packaging\fetch_model.py     # downloads + verifies the ~1GB bundled model
.venv\Scripts\pyinstaller.exe packaging/jobengine.spec --noconfirm
python packaging/smoke_test.py dist/JobEngine/JobEngine.exe   # must print PASS
# with Inno Setup installed:  iscc packaging\windows.iss
```

To also exercise the Apply Assist smoke check locally, install Chromium into
the exact directory the smoke test's frozen subprocess will look for before
running it (see `.github/workflows/release.yml`'s "Install Chromium for the
smoke test" step for the exact path derivation) — otherwise
`chromium-launch-selftest` in the smoke test output will fail, since Chromium
is an opt-in first-use download, not part of the base install.

## Why there's a smoke test

v0.4.0 shipped with every `jobspy` (Indeed) search silently failing on
installed copies: PyInstaller doesn't know to bundle a native DLL that
`jobspy`'s `tls_client` dependency loads via `ctypes` at a computed path
(invisible to static import analysis) — with no PyInstaller hook for that
package, the file was dropped, and every user saw "the specified module
could not be found" the moment a refresh ran. It never showed up in local
testing because dev-mode Python isn't frozen. **`packaging/smoke_test.py`
now runs as part of every CI release build** (`release.yml`) — it actually
launches the frozen exe, forces a refresh, and fails the build if the log
contains a missing-module signature. If you add a new dependency that loads
native binaries via `ctypes`/similar (check with
`find .venv/Lib/site-packages -iname "*.dll" -o -iname "*.so"`), add its data
files to `packaging/jobengine.spec` the same way (`collect_data_files`).

## Feature 005's two new native dependencies (same risk class, already handled)

`llama-cpp-python` (bundled local AI) and `playwright` (Apply Assist browser
automation) each load a compiled/driver binary the exact same
invisible-to-static-analysis way `tls_client` did. Both are already bundled
in `packaging/jobengine.spec` with a build-time assertion (fails the build
loudly if the lib/driver isn't found) **and** their own real-execution smoke
checks (`GET /api/diagnostics/local-llm-selftest` and
`.../chromium-launch-selftest` — genuine inference/launch calls, not import
checks). CI installs `llama-cpp-python` from a supplementary CPU-wheel index
(`--extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cpu`,
since it has no default PyPI wheel) with an import canary right after, and
installs Chromium into the smoke test's exact data directory before running
it — see `.github/workflows/release.yml`. The bundled model (`models/`,
fetched by `packaging/fetch_model.py`, gitignored) is cached across CI runs
via `actions/cache` keyed on a fixed model-version string, since it's a
~1GB download that doesn't change unless that key is bumped.
