> **Correction (see `patch-0.5.3.md`)**: the PATH-ambiguity theory below was
> wrong — `python -m pip` did not fix v0.5.1's mac-dmg build, which failed
> identically. The real cause was a corrupted wheel download
> (`zipfile.BadZipFile: Bad CRC-32`), found after adding a diagnostic
> annotation in v0.5.2. Kept here for the record of what was tried and
> ruled out, not as the actual explanation.

# Patch 0.5.1: Fix macOS release-build dependency install failure

**Reported**: 2026-07-20 — the v0.5.0 tag's "Release installers" workflow
succeeded completely on `windows-installer` (installer published, 1.2GB,
matching the expected size increase from the bundled model) but failed on
`mac-dmg` at the very first dependency-install step, 26 seconds in, exit
code 2.

## Root cause

Both jobs ran the identical line:

```
pip install -r requirements.txt pyinstaller --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cpu
```

GitHub's REST API does not expose raw step log text without elevated repo
access (confirmed 403 on both the job-logs endpoint and the check-run
annotations endpoint beyond a generic "exit code 2" message), so the exact
pip error could not be read directly. Exit code 2 specifically indicates a
pip *usage*-level failure rather than a resolution failure (`ERROR: No
matching distribution...` normally exits 1) — consistent with a bare `pip`
on the macOS runner resolving to an unexpected interpreter's pip rather
than the one `actions/setup-python@v5` just configured, a known class of
PATH-ordering issue on macOS runners that `windows-latest` (using pwsh,
which resolved `pip` correctly) did not hit.

Confirmed independently that the wheel itself is not the problem: the CPU
wheel index does publish `llama_cpp_python-0.3.34-py3-none-macosx_11_0_arm64.whl`,
matching `macos-latest`'s Apple Silicon runners.

## Fix

`.github/workflows/release.yml`, both jobs: replaced the single combined
`pip install ...` line with three explicit `python -m pip ...` steps
(upgrade pip, install requirements + the extra index, install pyinstaller
separately). `python -m pip` guarantees the pip tied to the exact Python
`actions/setup-python@v5` just set up is used, eliminating the PATH
ambiguity — the standard GitHub Actions mitigation for this exact class of
issue. Applied to both jobs for consistency, even though Windows already
worked.

## Verification

v0.5.0's Windows asset (`JobEngine-Setup-0.5.0.exe`, 1,206,531,457 bytes)
is already live and unaffected. Retagging as v0.5.1 rather than force-
pushing v0.5.0, per this project's established fix-and-retag pattern
(v0.4.0 → v0.4.1 → v0.4.2).

## Ship

Tagged `v0.5.1` to retry the macOS build with this fix; Windows rebuilds
too (harmless — same fix, and picks up the version bump).
