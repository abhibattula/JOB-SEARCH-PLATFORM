"""Build-time step: download + verify the bundled local LLM (feature 005).

Run before `pyinstaller packaging/jobengine.spec` — in CI (every tagged
release) and once locally by any dev building an installer. `models/` is
gitignored (a ~1GB binary has no place in the repo), so this script is the
single source of truth for getting the exact tested model onto disk.

Usage: python packaging/fetch_model.py
"""
from __future__ import annotations

import hashlib
import os
import sys
import urllib.request
from pathlib import Path

MODEL_URL = (
    "https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct-GGUF/resolve/main/"
    "qwen2.5-1.5b-instruct-q4_k_m.gguf"
)
MODEL_FILENAME = "qwen2.5-1.5b-instruct-q4_k_m.gguf"
# Verified by direct download + sha256sum (2026-07-20) — matches the
# repo's own X-Linked-ETag response header for this exact file.
EXPECTED_SHA256 = "6a1a2eb6d15622bf3c96857206351ba97e1af16c30d7a74ee38970e434e9407e"
EXPECTED_SIZE = 1_117_320_736

ROOT = Path(__file__).resolve().parents[1]
MODELS_DIR = ROOT / "models"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _already_verified(path: Path) -> bool:
    if not path.exists():
        return False
    if path.stat().st_size != EXPECTED_SIZE:
        return False
    return _sha256(path) == EXPECTED_SHA256


def _download(url: str, dest: Path) -> None:
    tmp = dest.with_suffix(dest.suffix + ".part")
    print(f"Downloading {url}\n  -> {dest} ...")
    req = urllib.request.Request(url, headers={"User-Agent": "JobEngine-build"})
    with urllib.request.urlopen(req, timeout=60) as resp, open(tmp, "wb") as out:
        total = int(resp.headers.get("Content-Length", 0))
        written = 0
        chunk_size = 1024 * 1024
        while True:
            chunk = resp.read(chunk_size)
            if not chunk:
                break
            out.write(chunk)
            written += len(chunk)
            if total:
                pct = written * 100 // total
                print(f"\r  {written // (1024*1024)}MB / {total // (1024*1024)}MB ({pct}%)",
                      end="", flush=True)
    print()
    tmp.replace(dest)


def main() -> int:
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    dest = MODELS_DIR / MODEL_FILENAME

    if _already_verified(dest):
        print(f"Model already present and verified: {dest}")
        return 0

    _download(MODEL_URL, dest)

    if dest.stat().st_size != EXPECTED_SIZE:
        print(
            f"FAIL: downloaded size {dest.stat().st_size} != expected {EXPECTED_SIZE}",
            file=sys.stderr,
        )
        return 1
    actual = _sha256(dest)
    if actual != EXPECTED_SHA256:
        print(
            f"FAIL: sha256 mismatch — expected {EXPECTED_SHA256}, got {actual}",
            file=sys.stderr,
        )
        dest.unlink(missing_ok=True)
        return 1

    print(f"OK: verified {dest} ({dest.stat().st_size} bytes, sha256 {actual})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
