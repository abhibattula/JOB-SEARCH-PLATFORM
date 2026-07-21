# Patch 0.5.3: The actual mac-dmg root cause, and a retry fix

**Context**: v0.5.1's `python -m pip` change (patch-0.5.1.md) did not fix
the mac-dmg build — it failed identically (~26s, same step). Rather than
guess a third time, v0.5.2 shipped as a diagnostic-only build: the
dependency-install step was changed to capture pip's actual output and
re-emit it as a GitHub Actions `::error::` annotation on failure, since the
check-runs annotations API (unlike raw job logs) is reachable without
elevated repo access.

## Root cause (confirmed from the v0.5.2 annotation)

```
zipfile.BadZipFile: Bad CRC-32 for file 'lib/libggml-base.0.16.0.dylib'
```

This is a **corrupted wheel download** — pip successfully resolved every
package (the annotation lists the full install queue: fastapi, pandas,
playwright, llama-cpp-python, keyring, ... all present) and failed while
unzipping `llama-cpp-python`'s wheel specifically, mid-way through
extracting its bundled `libggml-base` dylib. This is a transient
network/CDN integrity issue, not a configuration, resolver, or PATH
problem — both prior "fixes" (patch-0.5.1) were solving a problem that
didn't exist; the actual failure mode was never diagnosable from the
generic "exit code 2" the GitHub API surfaces for a failed step.

## Fix

`.github/workflows/release.yml`, both jobs: the dependency-install step now
retries up to 3 times (10s apart), passing `--no-cache-dir` on retries so
a corrupted file already written to pip's local cache can't be reused.
Only re-emits the `::error::` diagnostic annotation (introduced in v0.5.2)
if all 3 attempts fail, so a future genuine failure is still fully
diagnosable this way rather than reverting to an opaque exit code. Applied
to `windows-installer` too, even though it hasn't hit this — the failure
mode is a network issue, not platform-specific, so it could recur there.

## Verification

Tagging v0.5.3 to retry both builds. If corrupted-download theory holds,
this should now succeed outright (or on retry 2/3 at worst). If it fails
again, the `::error::` annotation will show the real cause directly rather
than requiring another diagnostic round-trip.

## Lesson

When a CI-only failure can't be diagnosed from the platform's exposed
status/exit-code (here: GitHub's REST API gates raw log access), don't
iterate fixes blind — instrument the failing step to self-report the
actual error through a channel that *is* reachable (a workflow annotation,
in this case) before attempting a second fix. The first attempt
(patch-0.5.1) was a reasonable hypothesis given the evidence available at
the time, but "the fix didn't work" should have triggered an instrumentation
step immediately rather than a second guess.
