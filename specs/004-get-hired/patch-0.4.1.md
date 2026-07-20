# Patch 0.4.1: Fix broken jobspy in installed builds

**Reported**: 2026-07-20 — user double-clicked the v0.4.0 `JobEngine.exe` and
saw "the specified module could not be found" as soon as a refresh ran.

## Root cause

`jobspy`'s dependency `tls_client` loads a native binary
(`tls-client-64.dll` / `.so` / `.dylib` depending on OS) via `ctypes` at a path
computed from the package's own install location. PyInstaller's static import
analysis has no way to see this (it isn't a Python import), and `tls_client`
ships no PyInstaller hook, so the file was silently excluded from every
frozen build — including all prior verification passes, which recorded
`jobspy: done, found=0` and were misread as "best-effort source, no results"
rather than "every search failed."

## Fix

- `packaging/jobengine.spec`: `collect_data_files("tls_client")` added to
  `datas`, with a build-time assertion that the native lib was actually found
  (fails the build loudly if this regresses).
- `packaging/smoke_test.py` (new): launches the real frozen exe in CI, forces
  a refresh, and fails the build if the log contains a missing-module
  signature. Wired into both jobs in `release.yml` before installer creation.
- `requirements.txt`: pinned to exact tested versions (previously unpinned,
  so CI could silently resolve different package versions than local dev).

## Verification

Reproduced 100% (confirmed via the actual downloaded v0.4.0 GitHub release
asset, fresh-installed and launched exactly like a user double-click — the
DLL traceback appeared in `app.log` on every jobspy search). After the fix:
two independent clean frozen launches show zero DLL errors in the log
(previously: every launch, every search, every time). `packaging/smoke_test.py`
passes locally against the fixed build and would have failed against v0.4.0.
143 unit/contract tests still green.

## Ship

Tagged `v0.4.1`; CI installers (now smoke-tested before upload) replace the
broken v0.4.0 assets.
