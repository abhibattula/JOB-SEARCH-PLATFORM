"""013 (Refinements): OS default-browser → Playwright channel order.

Pure, engine-only, no real registry — the ProgId read is injected. Guards the
blocking bug (Apply Assist opened Edge even when Chrome is the default) and the
cross-platform import safety (winreg must not be imported at module top level).
"""
from engine.autofill import default_browser as dbrow


def order(progid):
    return dbrow.default_channel_order(read_progid=lambda: progid)


def test_chrome_default_is_tried_first():
    o = order("ChromeHTML")
    assert o[0] == "chrome"
    assert "msedge" in o  # a fallback always exists


def test_edge_default_is_tried_first():
    o = order("MSEdgeHTM")
    assert o[0] == "msedge"
    assert "chrome" in o


def test_brave_maps_to_chrome_channel():
    assert order("BraveHTML")[0] == "chrome"


def test_unknown_progid_falls_back_to_default_order():
    o = order("FirefoxURL")
    assert set(o) >= {"chrome", "msedge"}   # both automatable channels present


def test_none_progid_falls_back():
    o = order(None)
    assert set(o) >= {"chrome", "msedge"}


def test_order_has_no_duplicates():
    assert len(order("ChromeHTML")) == len(set(order("ChromeHTML")))


def test_imports_and_returns_valid_order_off_windows(monkeypatch):
    """winreg is Windows-only; the module MUST import and produce a valid order
    on macOS/Linux/CI (Principle IV — engine runs headless/cross-platform)."""
    monkeypatch.setattr(dbrow.sys, "platform", "darwin")
    o = dbrow.default_channel_order()   # no injected reader → real default path
    assert set(o) >= {"chrome", "msedge"}


class TestPreference015:
    """015 (D3/FR-016/FR-018): preference-first channel order, Chrome by
    default; a live companion always beats the preference."""

    def test_preference_defaults_to_chrome(self, tmp_db):
        from engine import settings

        assert settings.get("PREFERRED_BROWSER") == "chrome"
        o = dbrow.effective_channel_order(read_progid=lambda: "MSEdgeHTM")
        assert o[0] == "chrome"          # preference beats the OS default
        assert "msedge" in o             # fallback always present

    def test_explicit_edge_preference_wins(self, tmp_db):
        from engine import settings

        settings.set("PREFERRED_BROWSER", "msedge")
        o = dbrow.effective_channel_order(read_progid=lambda: "ChromeHTML")
        assert o[0] == "msedge"

    def test_auto_follows_os_default(self, tmp_db):
        from engine import settings

        settings.set("PREFERRED_BROWSER", "auto")
        assert dbrow.effective_channel_order(
            read_progid=lambda: "MSEdgeHTM")[0] == "msedge"
        assert dbrow.effective_channel_order(
            read_progid=lambda: "ChromeHTML")[0] == "chrome"

    def test_bc_channel_order_uses_effective(self, tmp_db, monkeypatch):
        from engine.autofill import browser_controller as bc

        monkeypatch.setattr(dbrow, "effective_channel_order",
                            lambda read_progid=None: ("chrome", "msedge"))
        assert bc._channel_order() == ("chrome", "msedge")

    def test_companion_wins_regardless_of_preference(self, tmp_db):
        """FR-018 regression: a live companion beats every preference."""
        from engine import settings
        from engine.autofill import browser_controller as bc, ext_backend

        settings.set("PREFERRED_BROWSER", "msedge")
        ext_backend.register(lambda m: None, lambda code: None, "1.5.0",
                             browser="chrome")
        try:
            assert bc._choose_backend() == "extension"
        finally:
            ext_backend.reset_for_tests()


class TestOpenUrl015:
    """015 (FR-017): link opening honors the preference with a visible
    fallback — never a silent substitution."""

    def test_opens_preferred_browser_exe(self, tmp_db, monkeypatch):
        launched = []
        monkeypatch.setattr(
            dbrow, "_browser_exe",
            lambda channel: r"C:\Apps\chrome.exe" if channel == "chrome" else None)
        monkeypatch.setattr(dbrow.subprocess, "Popen",
                            lambda args, **kw: launched.append(list(args)))
        used = dbrow.open_url("https://example.com/j")
        assert used == "chrome"
        assert launched == [[r"C:\Apps\chrome.exe", "https://example.com/j"]]

    def test_missing_preferred_falls_back_to_os_default(self, tmp_db, monkeypatch):
        monkeypatch.setattr(dbrow, "_browser_exe", lambda channel: None)
        monkeypatch.setattr(dbrow.sys, "platform", "win32")
        opened = []
        monkeypatch.setattr(dbrow, "_open_with_os_default",
                            lambda url: opened.append(url))
        assert dbrow.open_url("https://x.example") == "os-default"
        assert opened == ["https://x.example"]

    def test_auto_never_looks_up_an_exe(self, tmp_db, monkeypatch):
        from engine import settings

        settings.set("PREFERRED_BROWSER", "auto")
        monkeypatch.setattr(
            dbrow, "_browser_exe",
            lambda channel: (_ for _ in ()).throw(
                AssertionError("auto must use the OS default handler")))
        opened = []
        monkeypatch.setattr(dbrow, "_open_with_os_default",
                            lambda url: opened.append(url))
        assert dbrow.open_url("https://x.example") == "os-default"
        assert opened == ["https://x.example"]
