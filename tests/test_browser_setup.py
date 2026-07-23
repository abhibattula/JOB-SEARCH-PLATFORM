"""008 (T007): browser_setup is now only the legacy-Chromium cleanup helper.

The 005-007 first-use Chromium download flow is gone — Apply Assist drives
the user's installed Edge/Chrome (see test_browser_channel.py). What remains
here: reporting and reclaiming the obsolete downloaded-browser directory
(offered from the Diagnostics page, FR-008)."""
from pathlib import Path

from engine.autofill import browser_setup


def _make_legacy_dir(tmp_path) -> Path:
    legacy = tmp_path / "browsers"
    (legacy / "chromium-1234").mkdir(parents=True)
    (legacy / "chromium-1234" / "chrome.exe").write_bytes(b"x" * 1024)
    (legacy / "apply-assist-profile").mkdir()
    (legacy / "apply-assist-profile" / "Cookies").write_bytes(b"y" * 256)
    return legacy


class TestLegacyCleanup:
    def test_size_zero_when_no_legacy_dir(self, tmp_db):
        assert browser_setup.legacy_size_bytes() == 0

    def test_size_reports_recursive_bytes(self, tmp_db, tmp_path):
        _make_legacy_dir(tmp_path)
        assert browser_setup.legacy_size_bytes() == 1024 + 256

    def test_cleanup_removes_dir_and_returns_freed(self, tmp_db, tmp_path):
        legacy = _make_legacy_dir(tmp_path)
        freed = browser_setup.cleanup_legacy()
        assert freed == 1024 + 256
        assert not legacy.exists()

    def test_cleanup_idempotent(self, tmp_db):
        assert browser_setup.cleanup_legacy() == 0

    def test_download_flow_is_gone(self):
        assert not hasattr(browser_setup, "start_install")
        assert not hasattr(browser_setup, "is_installed")
