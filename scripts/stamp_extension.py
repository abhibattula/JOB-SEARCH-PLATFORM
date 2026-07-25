"""Materialize the browser companion into the data dir and stamp
pairing.json (feature 010 T005; hardened in feature 015 T008).

The app OWNS the unpacked extension folder: the user loads
`<data_dir>/extension` in Chrome/Edge exactly once; every app launch
afterwards re-copies the (possibly updated) extension files and rewrites
pairing.json with the current port + bridge secret. Unpacked extensions
re-read packaged files from disk on every fetch, so this is the entire
pairing and update mechanism — no reload, no store, no user action.

015 hardening (FR-007/FR-008/FR-009/FR-015):
- imports are stdlib + engine.db/paths + bridge_const ONLY (AST-enforced) —
  the shipped 1.4.0 stamp died importing pydantic transitively and pairing
  failed silently;
- pairing.json is ALWAYS written, even when the file copy fails over an
  already-populated folder (stale ports kill the connection; old files
  merely lag);
- the written pairing is READ BACK and verified before success is claimed;
- every attempt records its outcome in `<data_dir>/stamp_status.json`
  (`ok/error/at/port/app_version/copy_warning`) — the doctor endpoint and
  the UI banner surface it, and the frozen smoke gate asserts it;
- the STAGED manifest.json version is rewritten to the app version, so a
  connected companion reports which release prepared it.

CLI for dev:  python -m scripts.stamp_extension --port 8000
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

from engine.autofill.bridge_const import APP_ID, PROTOCOL_V


def source_dir() -> Path:
    """The bundled extension source: repo checkout in dev, PyInstaller
    resource dir when frozen (same convention as fonts/models)."""
    from engine import paths

    if getattr(sys, "frozen", False):
        return paths.resource_path("extension")
    return Path(__file__).resolve().parent.parent / "extension"


def dest_dir() -> Path:
    from engine import paths

    return paths.data_dir() / "extension"


def status_path() -> Path:
    from engine import paths

    return paths.data_dir() / "stamp_status.json"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")


def write_status(ok: bool, error: str | None = None, port: int | None = None,
                 copy_warning: str | None = None) -> None:
    """Record the attempt's outcome. Best-effort by design: recording must
    never turn a working stamp into a failure."""
    from engine import APP_VERSION

    try:
        path = status_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({
            "ok": ok,
            "error": (error or None) and str(error)[:500],
            "at": _utc_now_iso(),
            "port": port,
            "app_version": APP_VERSION,
            "copy_warning": copy_warning,
        }), encoding="utf-8")
    except Exception:
        pass


def _verify_pairing(dest: Path, port: int, secret: str) -> None:
    """Read pairing.json back and prove it says what we meant (FR-007)."""
    data = json.loads((dest / "pairing.json").read_text(encoding="utf-8"))
    if (data.get("port") != port or data.get("secret") != secret
            or data.get("app_id") != APP_ID
            or data.get("protocol_v") != PROTOCOL_V):
        raise ValueError("pairing.json read-back mismatch after write")


def _stamp_manifest_version(dest: Path) -> None:
    """R13: the staged manifest tracks the app release that prepared it."""
    from engine import APP_VERSION

    manifest_path = dest / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["version"] = APP_VERSION
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")


def stamp(port: int) -> Path:
    """Copy the extension, write + verify pairing.json, record the outcome.
    Raises on failure (callers log); the outcome record is written either
    way, so a failure can never again be silent."""
    from engine import db

    src, dest = source_dir(), dest_dir()
    copy_warning: str | None = None

    try:
        dest.mkdir(parents=True, exist_ok=True)
        shutil.copytree(src, dest, dirs_exist_ok=True,
                        ignore=shutil.ignore_patterns("pairing.json"))
    except Exception as exc:
        if not (dest / "manifest.json").exists():
            # nothing usable on disk — this IS fatal
            write_status(ok=False, error=f"extension copy failed: {exc}",
                         port=port)
            raise
        # previous files remain loadable; a stale PORT would be fatal, stale
        # FILES are not — continue to the pairing write.
        copy_warning = f"copy failed, kept previous files: {exc}"

    try:
        secret = db.get_bridge_secret()
        pairing = {
            "port": port,
            "secret": secret,
            "app_id": APP_ID,
            "protocol_v": PROTOCOL_V,
        }
        (dest / "pairing.json").write_text(json.dumps(pairing), encoding="utf-8")
        if copy_warning is None:
            _stamp_manifest_version(dest)
        _verify_pairing(dest, port, secret)
    except Exception as exc:
        write_status(ok=False, error=str(exc), port=port,
                     copy_warning=copy_warning)
        raise

    write_status(ok=True, port=port, copy_warning=copy_warning)
    return dest


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    out = stamp(args.port)
    print(f"stamped {out} for port {args.port}")
