"""In-app self-update against GitHub Releases (feature 008, FR-030).

check() is best-effort and silent on any failure — an offline machine must
never notice this exists. The download path is a strict state machine
(idle → downloading → verifying → ready → installing / failed / blocked):
an installer NEVER executes unless its SHA-256 (published in the release
body by CI) verified — partial or tampered downloads are deleted, never
run. Windows installs hand off to Inno Setup silently and exit the app
(AppMutex + CloseApplications=yes are the safety net); macOS stays a
manual download (documented).
"""
from __future__ import annotations

import hashlib
import logging
import re
import sys
import threading

from . import APP_VERSION

log = logging.getLogger(__name__)

RELEASES_API = (
    "https://api.github.com/repos/abhibattula/JOB-SEARCH-PLATFORM/releases/latest"
)
RELEASES_PAGE = "https://github.com/abhibattula/JOB-SEARCH-PLATFORM/releases"


def _parse(version: str) -> tuple[int, ...] | None:
    match = re.fullmatch(r"v?(\d+)\.(\d+)\.(\d+)", (version or "").strip())
    if not match:
        return None
    return tuple(int(part) for part in match.groups())


def is_newer(candidate: str, than: str) -> bool:
    parsed_candidate, parsed_current = _parse(candidate), _parse(than)
    if parsed_candidate is None or parsed_current is None:
        return False
    return parsed_candidate > parsed_current


def _fetch_latest() -> dict:
    import httpx

    response = httpx.get(
        RELEASES_API,
        timeout=5,
        headers={"Accept": "application/vnd.github+json"},
        follow_redirects=True,
    )
    response.raise_for_status()
    return response.json()


def select_asset(release: dict, platform: str | None = None) -> dict | None:
    """The one artifact this platform installs: JobEngine-Setup-*.exe on
    Windows, JobEngine-*.dmg on macOS."""
    platform = platform or sys.platform
    for asset in release.get("assets") or []:
        name = asset.get("name") or ""
        if platform == "win32" and name.startswith("JobEngine-Setup-") and name.endswith(".exe"):
            return asset
        if platform == "darwin" and name.endswith(".dmg"):
            return asset
    return None


def expected_sha256(release: dict, asset_name: str) -> str | None:
    """CI publishes `<sha256>  <asset-name>` lines in the release body."""
    body = release.get("body") or ""
    match = re.search(
        rf"\b([0-9a-fA-F]{{64}})\s+{re.escape(asset_name)}\b", body
    )
    return match.group(1).lower() if match else None


def check(platform: str | None = None) -> dict | None:
    """Return {latest, url, newer, asset_*} or None when the check can't
    run. Caches the result for the download state machine."""
    try:
        release = _fetch_latest()
        tag = release.get("tag_name") or ""
        asset = select_asset(release, platform=platform)
        result = {
            "latest": tag.lstrip("v"),
            "url": release.get("html_url") or RELEASES_PAGE,
            "newer": is_newer(tag, than=APP_VERSION),
            "asset_name": asset.get("name") if asset else None,
            "asset_url": asset.get("browser_download_url") if asset else None,
            "size": asset.get("size") if asset else None,
            "sha256": expected_sha256(release, asset["name"]) if asset else None,
        }
        with _lock:
            _state["last_check"] = result
        return result
    except Exception:
        log.info("update check unavailable", exc_info=True)
        return None


# --- download / install state machine (FR-030) ------------------------------

_lock = threading.Lock()
_state: dict = {}


def reset_state() -> None:
    with _lock:
        _state.clear()
        _state.update({
            "state": "idle", "pct": 0, "error": None,
            "path": None, "version": None, "last_check": None,
        })


reset_state()


def progress() -> dict:
    with _lock:
        return {k: _state[k] for k in ("state", "pct", "error", "version")}


def _updates_dir():
    from . import paths

    directory = paths.data_dir() / "updates"
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def _stream_to(url: str, dest, on_progress) -> None:
    """Streams url to dest path with progress callbacks. Separated for
    testability; overwritten in unit tests."""
    import httpx

    with httpx.stream("GET", url, timeout=30, follow_redirects=True) as response:
        response.raise_for_status()
        total = int(response.headers.get("Content-Length") or 0)
        written = 0
        with open(dest, "wb") as out:
            for chunk in response.iter_bytes(1024 * 256):
                out.write(chunk)
                written += len(chunk)
                if total:
                    on_progress(written * 100 // total)


def _sha256_file(path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _run_download() -> None:
    with _lock:
        info = _state.get("last_check")
    if not info or not info.get("asset_url"):
        with _lock:
            _state.update(state="failed", error="no update information — run a check first")
        return
    dest = _updates_dir() / info["asset_name"]
    part = dest.with_suffix(dest.suffix + ".part")
    try:
        def on_progress(pct: int) -> None:
            with _lock:
                _state["pct"] = pct

        _stream_to(info["asset_url"], part, on_progress)
        with _lock:
            _state.update(state="verifying", pct=100)
        expected = info.get("sha256")
        if info.get("size") and part.stat().st_size != info["size"]:
            raise ValueError(
                f"size mismatch: got {part.stat().st_size}, expected {info['size']}"
            )
        if not expected:
            raise ValueError("release publishes no SHA-256 for this asset — refusing to verify")
        actual = _sha256_file(part)
        if actual != expected:
            raise ValueError(f"SHA-256 verification failed (got {actual[:12]}…)")
        part.replace(dest)  # only a fully-verified file ever gets the real name
        with _lock:
            _state.update(state="ready", path=str(dest), version=info["latest"], error=None)
    except Exception as exc:
        part.unlink(missing_ok=True)
        dest.unlink(missing_ok=True)
        log.warning("update download failed", exc_info=True)
        with _lock:
            _state.update(state="failed", error=str(exc)[:300])


def start_download(background: bool = True) -> bool:
    with _lock:
        if _state["state"] == "downloading":
            return False
        _state.update(state="downloading", pct=0, error=None, path=None)
    if background:
        threading.Thread(target=_run_download, daemon=True).start()
    else:
        _run_download()
    return True


def install() -> None:
    """Hand off to the verified installer and let the caller shut the app
    down. Windows only — macOS callers get the manual path (FR-030/T050)."""
    with _lock:
        state, path = _state["state"], _state["path"]
    if state != "ready" or not path:
        raise RuntimeError("no verified installer ready — download it first")
    if sys.platform != "win32":
        raise RuntimeError("in-app install is Windows-only — open the .dmg manually")
    import subprocess

    DETACHED_PROCESS = 0x00000008
    CREATE_NEW_PROCESS_GROUP = 0x00000200
    subprocess.Popen(
        [path, "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/STARTAPP=1"],
        creationflags=DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP,
        close_fds=True,
    )
    with _lock:
        _state["state"] = "installing"


def startup_check() -> dict | None:
    """Once-daily silent check (FR-030) — feeds the update banner."""
    from datetime import datetime, timezone

    from . import settings

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    if (settings.get("UPDATE_LAST_CHECK") or "") == today:
        return None
    settings.set("UPDATE_LAST_CHECK", today)
    return check()
