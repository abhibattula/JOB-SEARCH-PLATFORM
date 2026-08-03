"""022 "The Case File" — the design system, as a gate.

This module exists because of an audit, not a hunch. Before this feature,
roughly 35 class names were used in templates and defined in no stylesheet:
`.grid-2` x5 (so Profile's five "two-column" sections rendered as one stacked
column of ~50 fields), `.hint` x18, `.switch` (the escort toggle was a bare
browser checkbox), and nearly the whole Apply Assist review vocabulary —
the screen used *during* a live employer application.

Nothing caught it, because nothing looked. A string-presence assertion proves
a string exists; only a differencing check proves markup is styled.

Contract: specs/022-the-case-file/contracts/design-tokens.md (T1-T7).
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
CSS = ROOT / "web" / "static" / "styles.css"
TEMPLATES = ROOT / "web" / "templates"
PANEL_JS = ROOT / "extension" / "content" / "panel.js"

# The practice sandbox deliberately imitates Greenhouse/Workday markup and is
# a set of test fixtures (spec FR-047). Its classes are third-party names on
# purpose and must never be "fixed".
EXCLUDED_TEMPLATES = {
    "practice_apply.html", "practice_posting.html", "practice_frame.html",
}

# ---------------------------------------------------------------------------
# T005a — the shrinking allowlist.
#
# The design system lands over several phases, so "zero undefined classes"
# cannot be true until the last one. Asserting it early would leave the suite
# red for four phases, and a genuinely NEW breakage would be indistinguishable
# from the expected one.
#
# So: this set carries what is still known-undefined, and the test asserts it
# never GROWS. Red becomes a ratchet. Task T056 empties this set, at which
# point the assertion becomes the plain "zero undefined" gate (SC-001).
# ---------------------------------------------------------------------------
KNOWN_UNDEFINED: frozenset[str] = frozenset()
# T056: EMPTY. Every class used in every template now resolves to a rule
# (SC-001). The ratchet above is now the plain "zero undefined" gate the
# audit asked for, and any new undefined class fails the build immediately.


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
_JINJA = re.compile(r"\{\{.*?\}\}|\{%.*?%\}", re.S)
_LITERAL = re.compile(r"['\"]([^'\"]+)['\"]")
_COMPARISON = re.compile(r"(==|!=|>=|<=|\bin\b|\bis\b)")
_CLASSNAME = re.compile(r"^[a-z][a-z0-9_-]*$")


def _classes_in_value(value: str) -> set[str]:
    """Every class name a `class="..."` attribute can produce.

    Jinja makes this non-trivial: `class="sort {{ 'active' if sort == 'date' }}"`
    yields both a static name and a conditional one, and 'date' in that
    expression is a VALUE, not a class. Literals are therefore taken only from
    the left of a comparison operator.
    """
    found: set[str] = set()
    for block in _JINJA.findall(value):
        left = _COMPARISON.split(block, maxsplit=1)[0]
        for literal in _LITERAL.findall(left):
            for piece in literal.split():
                found.add(piece.lower())
    for token in _JINJA.sub(" ", value).split():
        found.add(token.lower())
    return {c for c in found if _CLASSNAME.match(c) and not c.endswith("-")}


def _template_files() -> list[Path]:
    return sorted(p for p in TEMPLATES.rglob("*.html")
                  if p.name not in EXCLUDED_TEMPLATES)


def used_classes() -> dict[str, set[str]]:
    """class name -> set of template names using it."""
    where: dict[str, set[str]] = {}
    for path in _template_files():
        text = path.read_text(encoding="utf-8", errors="replace")
        for value in re.findall(r'class\s*=\s*"([^"]*)"', text):
            for name in _classes_in_value(value):
                where.setdefault(name, set()).add(path.name)
    return where


def _css_text() -> str:
    return CSS.read_text(encoding="utf-8")


def defined_classes() -> set[str]:
    return set(re.findall(r"\.([A-Za-z][\w-]*)", _css_text()))


def _token_blocks(css: str) -> str:
    """Only the :root / [data-theme] / prefers-color-scheme declarations.

    Colour literals are legal here and nowhere else (T2).
    """
    out = []
    for match in re.finditer(
        r"(?::root|\[data-theme=[^\]]+\]|@media\s*\(prefers-color-scheme[^)]*\))"
        r"[^{]*\{",
        css,
    ):
        start = match.end() - 1
        depth, i = 0, start
        while i < len(css):
            if css[i] == "{":
                depth += 1
            elif css[i] == "}":
                depth -= 1
                if depth == 0:
                    break
            i += 1
        out.append(css[start:i + 1])
    return "\n".join(out)


_HEX = re.compile(r"#[0-9a-fA-F]{3,8}\b")
_FUNC_COLOR = re.compile(r"\b(?:rgba?|hsla?)\s*\(", re.I)


# ---------------------------------------------------------------------------
# WCAG 2.1 relative luminance and contrast.
# Fifteen lines of arithmetic instead of a dependency (Principle II).
# ---------------------------------------------------------------------------
def _srgb_to_linear(channel: float) -> float:
    return channel / 12.92 if channel <= 0.04045 else \
        ((channel + 0.055) / 1.055) ** 2.4


def relative_luminance(hex_color: str) -> float:
    raw = hex_color.lstrip("#")
    if len(raw) == 3:
        raw = "".join(c * 2 for c in raw)
    r, g, b = (int(raw[i:i + 2], 16) / 255 for i in (0, 2, 4))
    return (0.2126 * _srgb_to_linear(r)
            + 0.7152 * _srgb_to_linear(g)
            + 0.0722 * _srgb_to_linear(b))


def contrast_ratio(fg: str, bg: str) -> float:
    a, b = relative_luminance(fg), relative_luminance(bg)
    lighter, darker = max(a, b), min(a, b)
    return (lighter + 0.05) / (darker + 0.05)


def _declarations_in(selector_pattern: str) -> dict[str, str]:
    """Every custom-property declaration in one theme block, hex or not.

    Name-set comparison must use this, not the hex-only view below: a token
    declared as `--line-strong: var(--ink)` is still declared, and filtering
    it out would report a phantom mismatch between the themes.
    """
    css = _css_text()
    match = re.search(selector_pattern + r"[^{]*\{", css)
    if not match:
        return {}
    start = match.end() - 1
    depth, i = 0, start
    while i < len(css):
        if css[i] == "{":
            depth += 1
        elif css[i] == "}":
            depth -= 1
            if depth == 0:
                break
        i += 1
    block = css[start:i + 1]
    return {name: value.strip()
            for name, value in re.findall(r"(--[\w-]+)\s*:\s*([^;]+);", block)}


def _tokens_for(selector_pattern: str) -> dict[str, str]:
    """Token name -> hex value, for contrast arithmetic only."""
    return {name: value
            for name, value in _declarations_in(selector_pattern).items()
            if _HEX.fullmatch(value)}


# Pairings the design actually declares. Body text needs 4.5:1 (WCAG 1.4.3);
# UI component boundaries need 3:1 (WCAG 1.4.11).
#
# `--rule` is deliberately NOT here. It draws decorative hairlines between
# table rows and around cards, where the information is carried by position,
# not by the line. WCAG 1.4.11 covers boundaries needed to *identify* a
# component; forcing 3:1 on a row separator would mean heavy grey rules
# through every table for no accessibility gain. `--edge` is the token for
# real control boundaries, and it is asserted.
AA_PAIRS = [
    ("--ink", "--paper", 4.5), ("--ink", "--leaf", 4.5),
    ("--ink-soft", "--paper", 4.5), ("--ink-soft", "--leaf", 4.5),
    ("--seal", "--paper", 4.5), ("--seal", "--leaf", 4.5),
    ("--pencil", "--paper", 4.5), ("--pencil", "--leaf", 4.5),
    ("--flag", "--paper", 4.5), ("--flag", "--leaf", 4.5),
    ("--stop", "--paper", 4.5), ("--stop", "--leaf", 4.5),
    ("--edge", "--paper", 3.0), ("--edge", "--leaf", 3.0),
]

THEMES = {
    "light": r":root",
    "dark": r"\[data-theme=\"dark\"\]",
}


# ---------------------------------------------------------------------------
# T1 — every class used in a template is defined
# ---------------------------------------------------------------------------
class TestEveryClassIsDefined:
    def test_no_new_undefined_class_appears(self):
        """The ratchet. This set may shrink; it may never grow."""
        used, defined = used_classes(), defined_classes()
        undefined = {c for c in used if c not in defined}
        new = undefined - KNOWN_UNDEFINED
        assert not new, (
            "Class names used in markup with no definition in styles.css:\n"
            + "\n".join(f"  .{c}  ({', '.join(sorted(used[c]))})"
                        for c in sorted(new))
            + "\n\nEither define them, or -- if genuinely intentional -- add "
              "them to KNOWN_UNDEFINED with a reason."
        )

    def test_the_allowlist_does_not_outlive_its_purpose(self):
        """Anything that got defined must leave the allowlist, so the set
        never quietly rots into a permanent exception list."""
        defined = defined_classes()
        stale = {c for c in KNOWN_UNDEFINED if c in defined}
        assert not stale, (
            f"Now defined, so remove from KNOWN_UNDEFINED: {sorted(stale)}")


# ---------------------------------------------------------------------------
# T2 — no colour literal outside the token blocks
# ---------------------------------------------------------------------------
class TestColourLivesOnlyInTokens:
    def test_stylesheet_has_no_raw_colour_outside_the_token_blocks(self):
        css = _css_text()
        tokens = _token_blocks(css)
        body = css
        for block in tokens.split("\n"):
            if block.strip():
                body = body.replace(block, "")
        offenders = sorted(set(_HEX.findall(body)))
        assert not offenders, (
            f"Raw colour outside the token block: {offenders}. "
            "Every colour must come from a token (contract T2).")

    @pytest.mark.xfail(
        strict=True,
        reason="Phase 7 (T060) replaces the panel's hardcoded GitHub-dark "
               "block with the injected tokens. strict=True means this "
               "STARTS FAILING the moment the panel is fixed, which is the "
               "signal to delete this marker -- it cannot rot into a "
               "permanent exemption.")
    def test_panel_has_no_raw_colour(self):
        js = PANEL_JS.read_text(encoding="utf-8", errors="replace")
        style = "\n".join(re.findall(r"`([^`]*)`", js, re.S))
        offenders = sorted(set(_HEX.findall(style)))
        assert not offenders, (
            f"The browser panel still hardcodes colour: {offenders[:12]}. "
            "It must consume the same tokens as the app (contract T2/T7).")


# ---------------------------------------------------------------------------
# T3/T4 — every referenced token exists, in both themes
# ---------------------------------------------------------------------------
class TestTokensResolve:
    def test_every_referenced_token_is_defined(self):
        css = _css_text()
        referenced = set(re.findall(r"var\(\s*(--[\w-]+)", css))
        declared = set(re.findall(r"(--[\w-]+)\s*:", css))
        missing = sorted(referenced - declared)
        assert not missing, (
            f"var() references a token that is never defined: {missing}. "
            "This is exactly the --bg / --border bug that made the sticky "
            "Apply Assist bar render white in dark mode since 017.")

    def test_dark_rebinds_every_colour_token(self):
        """Colour tokens must exist in both themes. Spacing, type, radii and
        motion legitimately live in :root alone -- they are theme-independent,
        and demanding they be repeated would be noise, not a contract."""
        light_colours = set(_tokens_for(THEMES["light"]))
        dark = set(_declarations_in(THEMES["dark"]))
        assert light_colours, "the light theme must declare colour tokens"
        unbound = sorted(light_colours - dark)
        assert not unbound, (
            f"colour tokens with no dark binding: {unbound}. "
            "A token that exists in one theme only will render a light "
            "value on a dark surface.")


# ---------------------------------------------------------------------------
# T5 — contrast, in both themes
# ---------------------------------------------------------------------------
class TestContrast:
    @pytest.mark.parametrize("theme", sorted(THEMES))
    def test_declared_pairings_meet_wcag_aa(self, theme):
        tokens = _tokens_for(THEMES[theme])
        assert tokens, f"no tokens found for the {theme} theme"
        failures = []
        for fg, bg, minimum in AA_PAIRS:
            if fg not in tokens or bg not in tokens:
                continue
            ratio = contrast_ratio(tokens[fg], tokens[bg])
            if ratio < minimum:
                failures.append(
                    f"{fg} on {bg}: {ratio:.2f}:1 (needs {minimum}:1)")
        assert not failures, f"{theme} theme fails AA:\n  " + "\n  ".join(failures)


# ---------------------------------------------------------------------------
# T6 — nothing is fetched from a network; T7 — fonts degrade
# ---------------------------------------------------------------------------
class TestFullyOffline:
    def test_no_external_url_in_the_stylesheet(self):
        urls = re.findall(r"url\(\s*['\"]?(https?:|//)", _css_text())
        assert not urls, (
            "The stylesheet reaches a network. The app must work offline "
            "with no key and no connection (Principle II).")

    def test_no_external_stylesheet_or_font_in_any_template(self):
        offenders = []
        for path in _template_files():
            text = path.read_text(encoding="utf-8", errors="replace")
            for tag in re.findall(r"<link[^>]+>", text):
                if re.search(r'href\s*=\s*"(https?:|//)', tag):
                    offenders.append(f"{path.name}: {tag[:90]}")
        assert not offenders, "External asset reference:\n  " + \
            "\n  ".join(offenders)

    def test_every_font_face_source_exists_on_disk(self):
        css = _css_text()
        sources = re.findall(r"@font-face\s*\{[^}]*?url\(\s*['\"]?([^'\")]+)",
                             css, re.S)
        if not sources:
            pytest.skip("no @font-face declared yet")
        for src in sources:
            resolved = (CSS.parent / src.lstrip("/")).resolve() \
                if not src.startswith("/") else (ROOT / "web" / src.lstrip("/"))
            assert resolved.exists(), f"@font-face src missing on disk: {src}"

    def test_every_font_stack_ends_in_a_system_fallback(self):
        """FR-007: a missing font file must degrade, never break layout."""
        css = _css_text()
        stacks = re.findall(r"--(?:sans|mono|display|body|data)\s*:\s*([^;]+);",
                            css)
        if not stacks:
            pytest.skip("no font stack tokens declared yet")
        generic = ("sans-serif", "serif", "monospace", "system-ui",
                   "ui-monospace", "ui-sans-serif")
        for stack in stacks:
            assert any(g in stack for g in generic), (
                f"font stack has no system fallback: {stack.strip()}")
