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
- First run: upload a resume and (optionally) paste a free Groq API key on the
  Settings page to unlock AI match scores. Everything else works without it.

## Local Windows-only build (optional, for testing)

```powershell
.venv\Scripts\python.exe -m pip install pyinstaller
.venv\Scripts\pyinstaller.exe packaging/jobengine.spec --noconfirm
python packaging/smoke_test.py dist/JobEngine/JobEngine.exe   # must print PASS
# with Inno Setup installed:  iscc packaging\windows.iss
```

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
