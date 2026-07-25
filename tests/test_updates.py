"""004-WS-F: release update check against GitHub."""
from engine import updates


class TestVersionCompare:
    def test_newer_detection(self):
        assert updates.is_newer("0.4.0", than="0.3.0") is True
        assert updates.is_newer("v0.4.0", than="0.3.0") is True
        assert updates.is_newer("0.3.0", than="0.3.0") is False
        assert updates.is_newer("0.3.1", than="0.10.0") is False
        assert updates.is_newer("1.0.0", than="0.9.9") is True
        assert updates.is_newer("garbage", than="0.3.0") is False


class TestCheck:
    def test_reports_newer_release(self, monkeypatch):
        monkeypatch.setattr(
            updates, "_fetch_latest",
            lambda: {"tag_name": "v9.9.9", "html_url": "https://example/rel"},
        )
        result = updates.check()
        assert result["newer"] is True
        assert result["latest"] == "9.9.9"
        assert result["url"] == "https://example/rel"

    def test_current_version_is_not_newer(self, monkeypatch):
        from engine import APP_VERSION

        monkeypatch.setattr(
            updates, "_fetch_latest",
            lambda: {"tag_name": f"v{APP_VERSION}", "html_url": "u"},
        )
        assert updates.check()["newer"] is False

    def test_network_failure_is_silent(self, monkeypatch):
        def boom():
            raise RuntimeError("offline")

        monkeypatch.setattr(updates, "_fetch_latest", boom)
        assert updates.check() is None


# --- 008 US5 (T043): self-update — asset selection, integrity, state machine
import hashlib
import json

import pytest


RELEASE = {
    "tag_name": "v9.9.9",
    "html_url": "https://github.com/x/releases/tag/v9.9.9",
    "body": (
        "## What's new\nStuff.\n\n"
        "SHA-256:\n```\n"
        "0f343b0931126a20f133d67c2b018a3b1b0b6e6b0b6e6b0b6e6b0b6e6b0b6e6b  JobEngine-Setup-9.9.9.exe\n"
        "aaaa000000000000000000000000000000000000000000000000000000000000  JobEngine-9.9.9.dmg\n"
        "```\n"
    ),
    "assets": [
        {"name": "JobEngine-Setup-9.9.9.exe", "size": 12345,
         "browser_download_url": "https://gh/dl/JobEngine-Setup-9.9.9.exe"},
        {"name": "JobEngine-9.9.9.dmg", "size": 999,
         "browser_download_url": "https://gh/dl/JobEngine-9.9.9.dmg"},
    ],
}


@pytest.fixture(autouse=True)
def _reset_state(tmp_db):
    updates.reset_state()
    yield
    updates.reset_state()


class TestAssetSelection:
    def test_windows_picks_setup_exe(self):
        asset = updates.select_asset(RELEASE, platform="win32")
        assert asset["name"] == "JobEngine-Setup-9.9.9.exe"

    def test_macos_picks_dmg(self):
        asset = updates.select_asset(RELEASE, platform="darwin")
        assert asset["name"] == "JobEngine-9.9.9.dmg"

    def test_expected_sha256_parsed_from_release_body(self):
        sha = updates.expected_sha256(RELEASE, "JobEngine-Setup-9.9.9.exe")
        assert sha == "0f343b0931126a20f133d67c2b018a3b1b0b6e6b0b6e6b0b6e6b0b6e6b0b6e6b"
        assert updates.expected_sha256(RELEASE, "missing.exe") is None

    def test_check_includes_platform_asset(self, monkeypatch):
        monkeypatch.setattr(updates, "_fetch_latest", lambda: RELEASE)
        result = updates.check(platform="win32")
        assert result["newer"] is True
        assert result["asset_name"] == "JobEngine-Setup-9.9.9.exe"
        assert result["asset_url"].endswith(".exe")
        assert result["size"] == 12345
        assert result["sha256"].startswith("0f343b")


class TestDownloadStateMachine:
    def _release_with_real_hash(self, payload: bytes, actual: bytes | None = None):
        release = json.loads(json.dumps(RELEASE))
        digest = hashlib.sha256(payload).hexdigest()
        release["body"] = f"{digest}  JobEngine-Setup-9.9.9.exe"
        release["assets"][0]["size"] = len(actual if actual is not None else payload)
        return release

    def test_verified_download_reaches_ready(self, monkeypatch):
        payload = b"fake-installer-bytes"
        # 015: the incomplete-download floor is covered by its own test;
        # waive it here so the tiny fixture payload can reach verification
        monkeypatch.setattr(updates, "MIN_INSTALLER_BYTES", 1)
        release = self._release_with_real_hash(payload)
        monkeypatch.setattr(updates, "_fetch_latest", lambda: release)
        monkeypatch.setattr(
            updates, "_stream_to",
            lambda url, dest, on_progress: dest.write_bytes(payload),
        )
        updates.check(platform="win32")
        updates.start_download(background=False)
        progress = updates.progress()
        assert progress["state"] == "ready"
        assert progress["error"] is None

    def test_sha_mismatch_fails_and_deletes_file(self, monkeypatch):
        tampered = b"tampered-bytes"
        monkeypatch.setattr(updates, "MIN_INSTALLER_BYTES", 1)  # see above
        release = self._release_with_real_hash(b"the-real-bytes", actual=tampered)
        monkeypatch.setattr(updates, "_fetch_latest", lambda: release)
        monkeypatch.setattr(
            updates, "_stream_to",
            lambda url, dest, on_progress: dest.write_bytes(tampered),
        )
        updates.check(platform="win32")
        updates.start_download(background=False)
        progress = updates.progress()
        assert progress["state"] == "failed"
        assert "verif" in progress["error"].lower() or "sha" in progress["error"].lower()
        from engine import paths

        assert list((paths.data_dir() / "updates").glob("*.exe")) == []

    def test_install_refused_unless_ready(self):
        with pytest.raises(RuntimeError):
            updates.install()

    def test_startup_check_throttled_to_daily(self, monkeypatch):
        calls = []

        def fake_check(platform=None):
            calls.append(1)
            return {"newer": False, "latest": "0.0.0"}

        monkeypatch.setattr(updates, "check", fake_check)
        updates.startup_check()
        updates.startup_check()
        assert len(calls) == 1  # second same-day call skipped


class TestDownloadHardening015:
    """015 (FR-021/FR-022): the two evidenced updater failures — an empty
    download hashed into a baffling message, and a locked-file cleanup that
    crashed the thread — plus the ~6GB installer hoard."""

    def _seed_check(self, size=None, sha="a" * 64,
                    name="JobEngine-Setup-9.9.9.exe"):
        updates.reset_state()
        with updates._lock:
            updates._state["last_check"] = {
                "latest": "9.9.9", "newer": True, "asset_name": name,
                "asset_url": "https://example.com/dl.exe",
                "size": size, "sha256": sha,
            }

    def test_empty_download_rejected_before_hashing(self, tmp_db, monkeypatch):
        from pathlib import Path

        self._seed_check(size=None)
        monkeypatch.setattr(updates, "_stream_to",
                            lambda url, dest, cb: Path(dest).write_bytes(b""))
        hashed = []
        monkeypatch.setattr(updates, "_sha256_file",
                            lambda p: hashed.append(p) or "a" * 64)
        updates.start_download(background=False)
        prog = updates.progress()
        assert prog["state"] == "failed"
        assert "incomplete" in (prog["error"] or "")
        assert hashed == []  # never hash an empty file into 'e3b0c442…'

    def test_locked_cleanup_defers_instead_of_crashing(self, tmp_db, monkeypatch):
        import json as json_mod

        monkeypatch.setattr(updates.time, "sleep", lambda s: None)

        class Locked:
            attempts = 0

            def unlink(self, missing_ok=False):
                Locked.attempts += 1
                raise OSError(32, "used by another process")

            def __str__(self):
                return r"C:\fake\JobEngine-Setup-1.0.0.exe.part"

        updates._safe_unlink(Locked())
        assert Locked.attempts == 3  # bounded retries, then deferred
        cleanup = json_mod.loads(
            (updates._updates_dir() / "cleanup.json").read_text(encoding="utf-8"))
        assert r"C:\fake\JobEngine-Setup-1.0.0.exe.part" in cleanup

    def test_deferred_cleanup_drains_on_next_launch(self, tmp_db):
        leftover = updates._updates_dir() / "stale.part"
        leftover.write_bytes(b"x")
        updates._defer_cleanup(leftover)
        updates.run_deferred_cleanup()
        assert not leftover.exists()
        assert not (updates._updates_dir() / "cleanup.json").exists()

    def test_prune_keeps_current_plus_newest_previous(self, tmp_db):
        import os

        d = updates._updates_dir()
        names = ["JobEngine-Setup-0.9.0.exe", "JobEngine-Setup-1.0.0.exe",
                 "JobEngine-Setup-1.0.1.exe", "JobEngine-Setup-1.4.0.exe"]
        for i, name in enumerate(names):
            path = d / name
            path.write_bytes(b"x")
            os.utime(path, (1000 + i, 1000 + i))
        updates._prune_old_installers(keep=2)
        left = sorted(x.name for x in d.glob("JobEngine-Setup-*.exe"))
        assert left == ["JobEngine-Setup-1.0.1.exe", "JobEngine-Setup-1.4.0.exe"]

    def test_startup_check_drains_cleanup_first(self, tmp_db, monkeypatch):
        ran = []
        monkeypatch.setattr(updates, "run_deferred_cleanup",
                            lambda: ran.append(1))
        monkeypatch.setattr(updates, "check", lambda: None)
        updates.startup_check()
        assert ran == [1]
