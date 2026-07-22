"""CI smoke test for the frozen build: launches the packaged exe, waits for it
to serve, and fails loudly if the log shows a missing-module/dll error — the
exact class of bug that shipped silently in v0.4.0 (jobspy's tls_client DLL
wasn't bundled, so every jobspy search failed with "the specified module
could not be found" and nobody caught it because the failure was swallowed
into a per-source "found: 0" that looked like normal best-effort behavior).

Usage: python packaging/smoke_test.py path/to/JobEngine(.exe)
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
import urllib.request

FATAL_LOG_PATTERNS = (
    "could not be found",
    "PyInstallerImportError",
    "ModuleNotFoundError",
    # 005: llama-cpp-python / Playwright native-dependency failure modes —
    # same risk class as the tls_client DLL that shipped broken in v0.4.0.
    "failed to load model",
    "error loading model",
    "DLL load failed",
)


def read_port(port_file: str) -> int | None:
    try:
        return int(open(port_file, encoding="utf-8").read().strip())
    except (FileNotFoundError, ValueError):
        return None


def _clear_stale_state(data_dir: str) -> None:
    """Wipe the smoke data dir for a truly fresh run. 008: no browsers/
    carve-out anymore — Apply Assist launches the machine's installed
    Edge/Chrome via Playwright channels (CI runner images ship both), so
    there is no downloaded-Chromium state to preserve."""
    if not os.path.isdir(data_dir):
        return
    for name in os.listdir(data_dir):
        path = os.path.join(data_dir, name)
        if os.path.isdir(path):
            shutil.rmtree(path, ignore_errors=True)
        else:
            os.remove(path)


def main() -> int:
    exe = sys.argv[1]
    data_dir = os.path.join(os.environ.get("RUNNER_TEMP", "."), "jobengine-smoke-data")
    _clear_stale_state(data_dir)
    env = {**os.environ, "JOBS_DATA_DIR": data_dir}

    proc = subprocess.Popen([exe], env=env)
    port_file = os.path.join(data_dir, "port.txt")
    port = None
    deadline = time.time() + 60
    while time.time() < deadline and port is None:
        time.sleep(2)
        if proc.poll() is not None:
            print(f"FAIL: process exited early, rc={proc.returncode}")
            return 1
        port = read_port(port_file)

    if port is None:
        proc.terminate()
        print(f"FAIL: {port_file} was never written within 60s (app.log below if present)")
        logpath = os.path.join(data_dir, "app.log")
        if os.path.exists(logpath):
            print(open(logpath, encoding="utf-8", errors="replace").read()[-3000:])
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

    # 005: a genuine local-model inference call, not just an import check —
    # this is the same blind spot that let tls_client ship broken in v0.4.0
    # (the failure was swallowed into a per-source "found: 0" that looked
    # like normal behavior). llama-cpp-python's native lib being silently
    # dropped would surface here as ok=False, not as a process crash.
    selftest_body = urllib.request.urlopen(
        base + "/api/diagnostics/local-llm-selftest", timeout=60
    ).read()
    selftest = json.loads(selftest_body)
    print(f"local-llm-selftest -> {selftest}")
    if not selftest.get("ok") or not selftest.get("reply"):
        proc.terminate()
        print(f"FAIL: local-llm-selftest did not return ok+reply: {selftest}")
        return 1

    # 007: same reasoning, for the bundled DejaVu fonts + fpdf2 — a real
    # render, so dropped font data files fail the release loudly instead
    # of surfacing as broken PDF downloads in production.
    pdf_body = urllib.request.urlopen(
        base + "/api/diagnostics/pdf-selftest", timeout=60
    ).read()
    pdf_selftest = json.loads(pdf_body)
    print(f"pdf-selftest -> {pdf_selftest}")
    if not pdf_selftest.get("ok") or pdf_selftest.get("bytes", 0) <= 1000:
        proc.terminate()
        print(f"FAIL: pdf-selftest did not return ok+bytes: {pdf_selftest}")
        return 1

    # 005/008: same reasoning, for the Playwright driver — 008 launches the
    # machine's installed Edge/Chrome via channels (no download), so this
    # exercises the bundled Node driver against a real branded browser.
    chromium_body = urllib.request.urlopen(
        base + "/api/diagnostics/chromium-launch-selftest", timeout=60
    ).read()
    chromium_selftest = json.loads(chromium_body)
    print(f"chromium-launch-selftest -> {chromium_selftest}")
    if not chromium_selftest.get("ok"):
        proc.terminate()
        print(f"FAIL: chromium-launch-selftest did not return ok: {chromium_selftest}")
        return 1

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
