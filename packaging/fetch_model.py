"""Build-time step: download + verify the bundled model files.

Run before `pyinstaller packaging/jobengine.spec` — in CI (every tagged
release) and once locally by any dev building an installer. `models/` is
gitignored (GB-scale binaries have no place in the repo), so this script is
the single source of truth for getting the exact tested models onto disk.

Bundled models (008):
  - Qwen2.5-1.5B-Instruct Q4_K_M — offline LLM tier (feature 005)
  - EmbeddingGemma-300M Q8_0     — offline semantic pre-ranking (feature 008)

Usage: python packaging/fetch_model.py
"""
from __future__ import annotations

import hashlib
import sys
import urllib.request
from pathlib import Path

MODELS = [
    {
        "filename": "qwen2.5-1.5b-instruct-q4_k_m.gguf",
        "url": (
            "https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct-GGUF/resolve/main/"
            "qwen2.5-1.5b-instruct-q4_k_m.gguf"
        ),
        # Verified by direct download + sha256sum (2026-07-20) — matches the
        # repo's own X-Linked-ETag response header for this exact file.
        "sha256": "6a1a2eb6d15622bf3c96857206351ba97e1af16c30d7a74ee38970e434e9407e",
        "size": 1_117_320_736,
    },
    {
        "filename": "embeddinggemma-300M-Q8_0.gguf",
        "url": (
            "https://huggingface.co/ggml-org/embeddinggemma-300M-GGUF/resolve/main/"
            "embeddinggemma-300M-Q8_0.gguf"
        ),
        # Verified by direct download + Get-FileHash (2026-07-22).
        "sha256": "b5ce9d77a3fc4b3b39ccb5643c36777911cc4eb46a66962eadfa3f5f60490d63",
        "size": 333_590_944,
    },
]

ROOT = Path(__file__).resolve().parents[1]
MODELS_DIR = ROOT / "models"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _already_verified(path: Path, spec: dict) -> bool:
    if not path.exists():
        return False
    if path.stat().st_size != spec["size"]:
        return False
    return _sha256(path) == spec["sha256"]


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


def _fetch(spec: dict) -> bool:
    dest = MODELS_DIR / spec["filename"]
    if _already_verified(dest, spec):
        print(f"Already present and verified: {dest}")
        return True
    _download(spec["url"], dest)
    if dest.stat().st_size != spec["size"]:
        print(
            f"FAIL: {dest.name} size {dest.stat().st_size} != expected {spec['size']}",
            file=sys.stderr,
        )
        return False
    actual = _sha256(dest)
    if actual != spec["sha256"]:
        print(
            f"FAIL: {dest.name} sha256 mismatch — expected {spec['sha256']}, got {actual}",
            file=sys.stderr,
        )
        dest.unlink(missing_ok=True)
        return False
    print(f"OK: verified {dest} ({dest.stat().st_size} bytes, sha256 {actual})")
    return True


def main() -> int:
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    ok = all(_fetch(spec) for spec in MODELS)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
