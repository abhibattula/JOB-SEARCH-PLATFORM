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

    # 013 (FR-012): the app icon ships and is served as the favicon.
    fav = urllib.request.urlopen(base + "/static/favicon.ico", timeout=10)
    fav_head = fav.read(4)
    print(f"GET /static/favicon.ico -> {fav.status} magic={fav_head[:4]!r}")
    if fav.status != 200 or fav_head[:4] != b"\x00\x00\x01\x00":  # ICO magic
        proc.terminate()
        print("FAIL: favicon.ico missing or not a valid .ico")
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

    # 016 (T023, RC5): the riskiest generation in the app — grammar-
    # constrained JSON via the isolated AI runtime. Tailoring had NEVER
    # completed on the user's machine (the process died mid-inference with
    # nothing logged); completing here, with the app still serving after,
    # is the containment proof. Runs under the new default isolation.
    tailor_body = urllib.request.urlopen(
        base + "/api/diagnostics/tailor-selftest", timeout=420
    ).read()
    tailor_selftest = json.loads(tailor_body)
    print(f"tailor-selftest -> {tailor_selftest}")
    if not tailor_selftest.get("completed"):
        proc.terminate()
        print(f"FAIL: tailor selftest did not complete: {tailor_selftest}")
        return 1
    if not tailor_selftest.get("isolated"):
        proc.terminate()
        print("FAIL: frozen app is not running the isolated AI runtime")
        return 1
    alive = urllib.request.urlopen(base + "/", timeout=10).status
    if alive != 200:
        proc.terminate()
        print("FAIL: app not serving after the tailor selftest")
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

    # 008: the bundled embeddings model must actually embed in the frozen
    # build (same dropped-native-lib blind spot as llama_cpp/tls_client).
    diag_body = urllib.request.urlopen(
        base + "/api/diagnostics/all", timeout=180
    ).read()
    diag = {c["name"]: c for c in json.loads(diag_body)["checks"]}
    print(f"diagnostics/all -> { {k: v['ok'] for k, v in diag.items()} }")
    for required in ("embeddings", "browser", "pdf"):
        if not diag.get(required, {}).get("ok"):
            proc.terminate()
            print(f"FAIL: diagnostics check {required!r} failed: {diag.get(required)}")
            return 1

    # 008: Apply Assist preflight must ANSWER (ok or a typed error) — a
    # silent hang here was exactly the v0.5-v0.7 failure mode.
    preflight_req = urllib.request.Request(
        base + "/api/autofill/preflight", method="POST"
    )
    preflight = json.loads(urllib.request.urlopen(preflight_req, timeout=120).read())
    print(f"autofill/preflight -> {preflight}")
    if "ok" not in preflight:
        proc.terminate()
        print(f"FAIL: preflight returned no verdict: {preflight}")
        return 1

    # 008: the update check must run inside the frozen build (asset
    # selection + version compare); offline it may return an error string,
    # but the endpoint itself must answer.
    update_req = urllib.request.Request(
        base + "/api/settings/check-update", method="POST"
    )
    update_body = urllib.request.urlopen(update_req, timeout=30).read()
    print(f"check-update -> {update_body[:200]!r}")

    # 009: the live fill engine's status contract + the import state
    # machine + the practice application must all exist in the frozen app.
    status_body = json.loads(
        urllib.request.urlopen(base + "/api/autofill/status", timeout=30).read()
    )
    print(f"autofill/status activity -> {status_body.get('activity')}")
    if "activity" not in status_body:
        proc.terminate()
        print("FAIL: autofill status payload lacks the 009 activity block")
        return 1
    import_status = json.loads(
        urllib.request.urlopen(base + "/api/profile/import/status", timeout=30).read()
    )
    print(f"profile/import/status -> {import_status}")
    if import_status.get("state") != "idle":
        proc.terminate()
        print(f"FAIL: import state machine not idle at startup: {import_status}")
        return 1
    practice_html = urllib.request.urlopen(
        base + "/practice/apply", timeout=30
    ).read().decode("utf-8", errors="replace")
    print(f"practice page -> {len(practice_html)} bytes")
    if 'name="first_name"' not in practice_html:
        proc.terminate()
        print("FAIL: practice application page missing or malformed")
        return 1

    # 010: the browser companion must be materialized + stamped in the
    # frozen build, the bridge must answer, and the new surfaces must serve.
    bridge = json.loads(
        urllib.request.urlopen(base + "/api/bridge/info", timeout=30).read()
    )
    print(f"bridge/info -> {bridge}")
    if bridge.get("app_id") != "jobengine" or "protocol_v" not in bridge:
        proc.terminate()
        print(f"FAIL: bridge info malformed: {bridge}")
        return 1
    ext_manifest = os.path.join(data_dir, "extension", "manifest.json")
    ext_pairing = os.path.join(data_dir, "extension", "pairing.json")
    print(f"companion stamped -> manifest={os.path.exists(ext_manifest)} "
          f"pairing={os.path.exists(ext_pairing)}")
    ext_guard = os.path.join(data_dir, "extension", "content", "click_guard.js")
    # 012: the discovery content script must ship too, or the browse-time badge
    # silently does nothing in the frozen build.
    ext_discovery = os.path.join(data_dir, "extension", "content", "discovery.js")
    # 016: the apply-opener must ship too, or postings never auto-open.
    ext_opener = os.path.join(data_dir, "extension", "content", "opener.js")
    if not (os.path.exists(ext_manifest) and os.path.exists(ext_pairing)
            and os.path.exists(ext_guard) and os.path.exists(ext_discovery)
            and os.path.exists(ext_opener)):
        proc.terminate()
        print("FAIL: companion extension not fully materialized "
              f"(manifest={os.path.exists(ext_manifest)} "
              f"pairing={os.path.exists(ext_pairing)} "
              f"click_guard={os.path.exists(ext_guard)} "
              f"discovery={os.path.exists(ext_discovery)} "
              f"opener={os.path.exists(ext_opener)})")
        return 1
    ext_manifest_data = json.loads(
        open(ext_manifest, encoding="utf-8").read())
    # 015 (R13): the STAMPED manifest tracks the app release that stamped it.
    if ext_manifest_data.get("version") != bridge.get("app_version"):
        proc.terminate()
        print(f"FAIL: stamped extension manifest version "
              f"{ext_manifest_data.get('version')} != app "
              f"{bridge.get('app_version')}")
        return 1

    # 015 (T021/SC-005): pairing preparation must have RUN AND VERIFIED in
    # THIS very launch — the 1.4.0 stamp death (pydantic_core import) was
    # invisible to every earlier gate. The doctor is the single truth the
    # wizard, diagnostics, and this gate all read.
    doctor = json.loads(
        urllib.request.urlopen(base + "/api/companion/doctor", timeout=30).read()
    )
    print(f"companion/doctor -> stamp={doctor.get('stamp')} "
          f"pairing={doctor.get('pairing')} port={doctor.get('port')}")
    if not (doctor.get("stamp") or {}).get("ok"):
        proc.terminate()
        print(f"FAIL: pairing preparation (stamp) not ok: {doctor.get('stamp')}")
        return 1
    if not (doctor.get("pairing") or {}).get("fresh"):
        proc.terminate()
        print("FAIL: pairing.json was not stamped by this launch (stale)")
        return 1
    if not (doctor.get("port") or {}).get("match"):
        proc.terminate()
        print(f"FAIL: pairing port does not match port.txt: {doctor.get('port')}")
        return 1
    if (doctor.get("stamp") or {}).get("app_version") != bridge.get("app_version"):
        proc.terminate()
        print("FAIL: stamp app_version does not match the running app")
        return 1
    # 019: the version-skew signal must EXIST in the frozen build. It is the
    # difference between "connected" and "connected but running last
    # release's code, quietly dropping answers" — and it is the kind of
    # thing that works in a source tree and is absent from a bundle.
    if "version_ok" not in doctor or "app_version" not in doctor:
        proc.terminate()
        print(f"FAIL: doctor has no version-skew signal: {sorted(doctor)}")
        return 1
    if doctor.get("app_version") != bridge.get("app_version"):
        proc.terminate()
        print("FAIL: doctor app_version disagrees with the bridge")
        return 1
    companion_html = urllib.request.urlopen(
        base + "/companion", timeout=30
    ).read().decode("utf-8", errors="replace")
    if "Load unpacked" not in companion_html:
        proc.terminate()
        print("FAIL: /companion walkthrough missing or malformed")
        return 1
    # 019: the escort's off switch and the auto-sign-in disclosure ship with
    # the app or the applicant cannot consent to, or revoke, what it does.
    settings_html = urllib.request.urlopen(
        base + "/settings", timeout=30
    ).read().decode("utf-8", errors="replace")
    for needle, what in (("escort-enabled", "the escort toggle"),
                         ("signs you in", "the auto-sign-in disclosure")):
        if needle not in settings_html:
            proc.terminate()
            print(f"FAIL: /settings is missing {what}")
            return 1
    # 019: the credential vault must import INSIDE the frozen app — keyring
    # cannot auto-detect its backend there, and a saved login that cannot be
    # read is a sign-in that silently never happens.
    from engine import credentials as _cred

    generated = _cred.generate_password()
    if len(generated) < 20:
        proc.terminate()
        print("FAIL: the frozen build cannot generate an account password")
        return 1
    next_actions = json.loads(
        urllib.request.urlopen(base + "/api/next-actions", timeout=30).read()
    )
    print(f"next-actions -> {next_actions}")
    if "actions" not in next_actions:
        proc.terminate()
        print("FAIL: /api/next-actions did not answer")
        return 1
    status_010 = json.loads(
        urllib.request.urlopen(base + "/api/autofill/status", timeout=30).read()
    )
    if "extension" not in status_010 or "backend" not in status_010:
        proc.terminate()
        print("FAIL: autofill status missing 010 backend/extension fields")
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
