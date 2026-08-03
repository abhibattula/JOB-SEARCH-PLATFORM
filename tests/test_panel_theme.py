"""022 Phase 7 — the browser panel joins the same product.

extension/content/panel.js hardcoded GitHub-dark (#0d1117, #238636, #3fb950,
#58a6ff) inside a shadow root opened with `all:initial`. It shared no token
with the app and could not follow the applicant's light/dark choice — and it
is the surface they spend the actual application in.

Contract: specs/022-the-case-file/contracts/panel-theme.md (P1-P6).
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PANEL = ROOT / "extension" / "content" / "panel.js"
BACKEND = ROOT / "engine" / "autofill" / "ext_backend.py"
PROTOCOL = ROOT / "engine" / "autofill" / "ext_protocol.py"


def _panel() -> str:
    return PANEL.read_text(encoding="utf-8", errors="replace")


class TestProtocolUnchanged:
    def test_protocol_version_is_still_one(self):
        """P1 — this is an ADDITIVE field, not a version bump.

        Read the value, don't grep the source: ext_protocol RE-EXPORTS
        PROTOCOL_V from bridge_const, so a regex over this file was checking
        somewhere the number does not live and would have passed whatever the
        real value became.
        """
        from engine.autofill.bridge_const import PROTOCOL_V

        assert PROTOCOL_V == 1, (
            "PROTOCOL_V must stay 1; the theme is an additive field")

    def test_theme_rides_on_messages_that_already_exist(self):
        """P2 — a new message type is a bigger compatibility surface than a
        field an older companion simply ignores."""
        text = BACKEND.read_text(encoding="utf-8")
        for carrier in ("watch_start", "overlay_state"):
            block = re.search(
                r'_outbound\(\s*"' + carrier + r'"[^)]*\)', text, re.S)
            assert block, f"{carrier} is not sent from ext_backend"
        assert "theme=" in text, (
            "no outbound message carries the theme")

    def test_the_theme_never_travels_with_a_secret(self):
        """P2/FR-046 — fill-and-forget is not negotiable."""
        text = BACKEND.read_text(encoding="utf-8")
        for match in re.finditer(r"_outbound\((.*?)\)\)", text, re.S):
            payload = match.group(1)
            if "theme=" not in payload:
                continue
            for forbidden in ("secret", "password", "credential", "token"):
                assert forbidden not in payload.lower(), (
                    f"a theme-carrying message also carries {forbidden!r}")


class TestPanelUsesTheAppsTokens:
    def test_no_github_dark_literals_remain(self):
        """P5 — the panel was a second, unrelated design system."""
        panel = _panel()
        for dead in ("#0d1117", "#238636", "#3fb950", "#58a6ff", "#30363d",
                     "#161b22", "#21262d", "#8b949e", "#9e2f24", "#2ea043"):
            assert dead not in panel, (
                f"{dead} is GitHub-dark; the panel must consume the app's "
                f"tokens")

    def test_the_panel_declares_the_same_token_names(self):
        """P5 — the shadow root cannot inherit through all:initial, so the
        tokens are injected. They must be the SAME names, or the two
        surfaces drift."""
        panel = _panel()
        for token in ("--paper", "--leaf", "--ink", "--ink-soft", "--rule",
                      "--seal", "--pencil", "--flag", "--stop"):
            assert token in panel, f"the panel does not define {token}"

    def test_the_panel_has_a_dark_binding(self):
        assert "--paper:" in _panel()
        assert _panel().count("--paper:") >= 2, (
            "the panel needs a light AND a dark value for every colour")


class TestThemeResolution:
    def test_an_explicit_choice_is_honoured(self):
        panel = _panel()
        assert re.search(r'theme\s*===?\s*["\']dark["\']', panel), (
            "the panel never reads an explicit dark choice")

    def test_it_falls_back_to_the_os_preference(self):
        """P3 — when no choice is expressed, and before any message has
        arrived."""
        assert "prefers-color-scheme" in _panel(), (
            "with no explicit theme the panel must follow the OS")


class TestTheStampIsShared:
    def test_the_panel_renders_the_provenance_treatments(self):
        """FR-018 — the same score must not read differently here."""
        panel = _panel()
        for ring in ("pencil", "ink", "sealed"):
            assert f"stamp--{ring}" in panel or f"'{ring}'" in panel, (
                f"the panel has no {ring} treatment")


class TestPositioningUntouched:
    def test_every_offset_is_still_important(self):
        """P6/FR-037 — the v1.0.0-v1.7.0 bug documented at panel.js:156.
        The 021 drag work depends on this and must not be disturbed."""
        panel = _panel()
        for prop in ("position", "z-index"):
            assert re.search(
                r'setProperty\(\s*["\']' + prop + r'["\'][^)]*"important"',
                panel), f"{prop} lost its !important"

    def test_the_shadow_root_still_isolates(self):
        assert "all:initial" in _panel().replace(" ", "")
