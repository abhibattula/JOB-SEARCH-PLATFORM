"""015 (US1/FR-005): unclean-exit detection via running.marker.

A native crash (the recorded ggml access violation) leaves no Python
traceback and no crash.marker — the app just vanishes. The lifecycle marker
is the honest signal: written at startup, removed only on a clean shutdown;
found at the NEXT startup ⇒ the previous session died.
"""
from engine import lifecycle, paths, settings


class TestLifecycleMarker:
    def test_first_start_is_clean_and_marks(self, tmp_db):
        assert lifecycle.startup_check_and_mark() is False
        assert (paths.data_dir() / "running.marker").exists()
        assert settings.get("UNCLEAN_EXIT_AT") in (None, "")

    def test_unclean_exit_detected_and_recorded(self, tmp_db):
        lifecycle.startup_check_and_mark()   # session 1 starts…
        # …and never calls clear_running() (crash) — session 2:
        assert lifecycle.startup_check_and_mark() is True
        assert settings.get("UNCLEAN_EXIT_AT")  # recorded for the banner

    def test_clean_shutdown_leaves_no_trace(self, tmp_db):
        lifecycle.startup_check_and_mark()
        lifecycle.clear_running()
        assert not (paths.data_dir() / "running.marker").exists()
        assert lifecycle.startup_check_and_mark() is False

    def test_desktop_entrypoint_is_wired(self):
        """Static guard: the desktop shell must mark at startup and clear on
        its clean-exit path — the marker is meaningless otherwise."""
        import pathlib

        src = pathlib.Path("desktop.py").read_text(encoding="utf-8")
        assert "startup_check_and_mark" in src
        assert "clear_running" in src
