"""CI smoke test for the frozen build: launches the packaged exe, waits for it
to serve, and fails loudly if the log shows a missing-module/dll error — the
exact class of bug that shipped silently in v0.4.0 (jobspy's tls_client DLL
wasn't bundled, so every jobspy search failed with "the specified module
could not be found" and nobody caught it because the failure was swallowed
into a per-source "found: 0" that looked like normal best-effort behavior).

Usage: python packaging/smoke_test.py path/to/JobEngine(.exe)
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import time
import urllib.request

FATAL_LOG_PATTERNS = (
    "could not be found",
    "PyInstallerImportError",
    "ModuleNotFoundError",
)


def find_listening_port(pid: int) -> int | None:
    if sys.platform == "win32":
        out = subprocess.run(["netstat", "-ano"], capture_output=True, text=True).stdout
        for match in re.finditer(
            r"127\.0\.0\.1:(\d+)\s+\S+\s+LISTENING\s+" + str(pid) + r"\b", out
        ):
            return int(match.group(1))
        return None
    out = subprocess.run(
        ["lsof", "-a", "-p", str(pid), "-iTCP", "-sTCP:LISTEN"], capture_output=True, text=True
    ).stdout
    match = re.search(r":(\d+)\s+\(LISTEN\)", out)
    return int(match.group(1)) if match else None


def main() -> int:
    exe = sys.argv[1]
    data_dir = os.path.join(os.environ.get("RUNNER_TEMP", "."), "jobengine-smoke-data")
    shutil.rmtree(data_dir, ignore_errors=True)
    env = {**os.environ, "JOBS_DATA_DIR": data_dir}

    proc = subprocess.Popen([exe], env=env)
    port = None
    deadline = time.time() + 60
    while time.time() < deadline and port is None:
        time.sleep(2)
        if proc.poll() is not None:
            print(f"FAIL: process exited early, rc={proc.returncode}")
            return 1
        port = find_listening_port(proc.pid)

    if port is None:
        proc.terminate()
        print("FAIL: app never started listening within 60s")
        return 1

    base = f"http://127.0.0.1:{port}"
    for path in ("/", "/settings", "/profile", "/analytics"):
        code = urllib.request.urlopen(base + path, timeout=10).status
        print(f"GET {path} -> {code}")
        if code != 200:
            proc.terminate()
            print(f"FAIL: {path} returned {code}")
            return 1

    # Force a refresh and wait briefly so any lazily-imported source (the
    # exact category of bug this test exists to catch) actually executes.
    req = urllib.request.Request(base + "/api/refresh?force=1", method="POST", data=b"")
    urllib.request.urlopen(req, timeout=10)
    time.sleep(45)

    proc.terminate()
    time.sleep(2)
    if proc.poll() is None:
        proc.kill()

    logpath = os.path.join(data_dir, "app.log")
    if os.path.exists(logpath):
        text = open(logpath, encoding="utf-8", errors="replace").read()
        hits = [p for p in FATAL_LOG_PATTERNS if p.lower() in text.lower()]
        if hits:
            print(f"FAIL: app.log contains fatal pattern(s) {hits}:\n{text[-3000:]}")
            return 1

    print("PASS: frozen app served all pages and completed a forced refresh cleanly")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
