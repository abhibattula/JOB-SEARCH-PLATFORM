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
