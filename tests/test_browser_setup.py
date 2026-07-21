"""005-T025: engine/autofill/browser_setup.py — first-use Chromium install.

Progress is tracked via the settings table (same DB-backed-KV pattern as
everything else in engine/settings.py), not by parsing Playwright's internal
directory layout — simpler and fully mockable in tests (no real ~200MB
download in the unit suite).
"""
import pytest

from engine.autofill import browser_setup


@pytest.fixture(autouse=True)
def _isolate(tmp_db):
    yield


class TestStatus:
    def test_not_installed_by_default(self, tmp_db):
        assert browser_setup.status() == "not_installed"

    def test_is_installed_false_by_default(self, tmp_db):
        assert browser_setup.is_installed() is False


class TestStartInstall:
    def test_start_install_runs_subprocess_and_marks_installed_on_success(self, tmp_db, monkeypatch):
        calls = []

        def fake_run(cmd, **kwargs):
            calls.append(cmd)

            class Result:
                returncode = 0
                stderr = ""

            return Result()

        monkeypatch.setattr(browser_setup.subprocess, "run", fake_run)

        browser_setup.start_install(background=False)

        assert browser_setup.status() == "installed"
        assert browser_setup.is_installed() is True
        assert any("chromium" in " ".join(str(c) for c in cmd) for cmd in calls)

    def test_start_install_marks_failed_on_nonzero_exit(self, tmp_db, monkeypatch):
        def fake_run(cmd, **kwargs):
            class Result:
                returncode = 1
                stderr = "network error"

            return Result()

        monkeypatch.setattr(browser_setup.subprocess, "run", fake_run)

        browser_setup.start_install(background=False)

        status = browser_setup.status()
        assert status.startswith("failed")
        assert browser_setup.is_installed() is False

    def test_start_install_marks_failed_on_exception(self, tmp_db, monkeypatch):
        def fake_run(cmd, **kwargs):
            raise OSError("no disk space")

        monkeypatch.setattr(browser_setup.subprocess, "run", fake_run)

        browser_setup.start_install(background=False)

        assert browser_setup.status().startswith("failed")

    def test_already_installed_is_a_noop(self, tmp_db, monkeypatch):
        calls = []
        monkeypatch.setattr(browser_setup, "status", lambda: "installed")

        started = browser_setup.start_install(background=False)

        assert started is False

    def test_install_uses_playwright_driver_executable_not_sys_executable(self, tmp_db, monkeypatch):
        """Regression test: sys.executable is the frozen app's own .exe inside
        a packaged build, not a Python interpreter — `[sys.executable, "-m",
        "playwright", ...]` silently does not install anything there (it just
        tries to relaunch the app). The real fix uses Playwright's own
        compute_driver_executable(), which resolves to its bundled Node.js
        driver directly and works identically in dev and frozen builds."""
        monkeypatch.setattr(
            browser_setup, "compute_driver_executable",
            lambda: ("/fake/node", "/fake/cli.js"),
        )
        calls = []

        def fake_run(cmd, **kwargs):
            calls.append(cmd)

            class Result:
                returncode = 0
                stderr = ""

            return Result()

        monkeypatch.setattr(browser_setup.subprocess, "run", fake_run)

        browser_setup.start_install(background=False)

        assert len(calls) == 1
        cmd = calls[0]
        assert cmd[0] == "/fake/node"
        assert cmd[1] == "/fake/cli.js"
        assert "install" in cmd
        assert "chromium" in cmd
        import sys as sys_mod
        assert sys_mod.executable not in cmd
