"""Materialize the browser companion into the data dir and stamp
pairing.json (feature 010, T005).

The app OWNS the unpacked extension folder: the user loads
`<data_dir>/extension` in Chrome exactly once; every app launch afterwards
re-copies the (possibly updated) extension files and rewrites pairing.json
with the current port + bridge secret. Unpacked extensions re-read
packaged files from disk on every fetch, so this is the entire pairing and
update mechanism — no reload, no store, no user action.

CLI for dev:  python -m scripts.stamp_extension --port 8000
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

APP_ID = "jobengine"


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


def stamp(port: int) -> Path:
    """Copy the extension and write pairing.json. Idempotent; the bridge
    secret is stable per machine (engine.db.get_bridge_secret)."""
    from engine import db
    from engine.autofill import ext_protocol

    src, dest = source_dir(), dest_dir()
    dest.mkdir(parents=True, exist_ok=True)
    shutil.copytree(src, dest, dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns("pairing.json"))
    pairing = {
        "port": port,
        "secret": db.get_bridge_secret(),
        "app_id": APP_ID,
        "protocol_v": ext_protocol.PROTOCOL_V,
    }
    (dest / "pairing.json").write_text(
        json.dumps(pairing), encoding="utf-8"
    )
    return dest


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    out = stamp(args.port)
    print(f"stamped {out} for port {args.port}")
