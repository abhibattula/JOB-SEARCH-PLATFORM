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
