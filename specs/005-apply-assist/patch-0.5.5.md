# Patch 0.5.5: The actual, confirmed root cause — corrupted upstream macOS wheels

**Context**: v0.5.1 through v0.5.4 iterated on the wrong theory (PATH
ambiguity, then a transient download blip) because GitHub's REST API only
exposes a generic "exit code N" for a failed step, with raw log text
gated behind repo-admin access this project doesn't have. v0.5.2 and
v0.5.4 built diagnostic instrumentation (a `::error::` annotation
containing the actual pip output, reachable via the check-runs API even
when raw logs aren't) specifically to stop guessing blind — that
instrumentation is what finally surfaced the real error text.

## What the annotation showed

```
zipfile.BadZipFile: Bad CRC-32 for file 'lib/libggml-base.0.16.0.dylib'
```

...on every one of 3 retry attempts, including with `--no-cache-dir`
forcing a genuinely fresh download each time. That ruled out "transient
network blip" — a real transient issue would not fail identically 3/3
times against 3 independent downloads.

## Independent verification (not just CI-log reading)

Reproduced directly from a dev machine, outside CI entirely:

1. `pip download llama-cpp-python==0.3.34 --platform macosx_11_0_arm64
   --only-binary=:all: --no-cache-dir` — downloaded fresh, hash
   `d42e069d...`, `zipfile.testzip()` reports the same corrupt file.
2. `curl` directly to the GitHub Releases asset URL
   (`github.com/abetlen/llama-cpp-python/releases/download/v0.3.34/...`),
   bypassing pip entirely — **identical hash**. This proves the corruption
   exists in the file as published, not introduced by pip, this project's
   CI, or any CDN edge in between.
3. Widened the check across recent releases (direct curl + zip integrity
   test for each): **0.3.34, 0.3.33, 0.3.32, 0.3.30, 0.3.28, 0.3.27 are all
   corrupted** (different files/CRCs each time — not one shared bad byte
   range, but a recurring defect in abetlen/llama-cpp-python's macOS
   arm64 wheel build/upload pipeline across many releases). **0.3.29 and
   0.3.26 verified zip-clean.**
4. Windows wheels were never affected — `windows-installer` succeeded on
   every single CI attempt (v0.5.0 through v0.5.4) using 0.3.34's Windows
   wheel, and a local install + real inference call against the bundled
   model was reverified working after this investigation.
5. Checked whether 0.3.29 could simply replace 0.3.34 everywhere: its
   *Windows* wheel installs but crashes with `OSError: [WinError
   -1073741795]` (STATUS_ILLEGAL_INSTRUCTION) on this dev machine's CPU —
   an unrelated, separate compatibility issue specific to older Windows
   builds' baseline CPU instruction assumptions. 0.3.26 hits the same
   crash. This does not implicate 0.3.29/0.3.26's *macOS* wheels (ARM64 has
   none of x86's microarchitecture-baseline fragmentation across GitHub's
   Apple Silicon runner fleet), but it does rule out simply downgrading
   the single shared pin — Windows must stay on 0.3.34.

## Fix

`requirements.txt`: `llama-cpp-python` is now pinned **per platform** via
a PEP 508 environment marker instead of one shared version:

```
llama-cpp-python==0.3.34; sys_platform == "win32"
llama-cpp-python==0.3.29; sys_platform == "darwin"
```

Verified locally: `pip install --dry-run -r requirements.txt` on this
Windows machine correctly reports `Ignoring llama-cpp-python: markers
'sys_platform == "darwin"' don't match your environment` and resolves
0.3.34 — the marker syntax works exactly as intended, not just in theory.

`packaging/jobengine.spec`'s native-lib assertion (`collect_dynamic_libs`
+ "any file ends in .dll/.so/.dylib") was already version-agnostic (no
hardcoded filename like `libggml-base.0.16.0.dylib`), so no change needed
there for the version bump.

The retry-loop and diagnostic-annotation machinery added in v0.5.3/v0.5.4
stays in the workflow — it didn't fix *this* failure (a permanently
corrupted source file can't be retried away), but it's a real capability
worth keeping for any future *genuinely* transient dependency-install
failure, on either platform.

## Lesson

"The fix didn't work, try a different fix" isn't enough when the platform
itself won't tell you why — at that point, stop guessing and build a path
to the real evidence first (here: an annotation channel that bypasses the
log-access gate), *then* verify the resulting diagnosis independently
before shipping a fix (here: reproducing the corruption from a completely
separate machine and tool, and separately confirming the proposed
replacement version doesn't just move the problem elsewhere).

## Ship

Tagged v0.5.5. Expect both jobs to succeed now — mac-dmg installing a
verified-clean wheel, windows-installer unchanged (already proven working
5 times over).
