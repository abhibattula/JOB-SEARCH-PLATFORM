"""022 Phase 5 — the Apply Assist review list, which had no CSS at all.

This is the screen the applicant reads DURING a live employer application, and
every class it used was undefined: .answers-review, .answer-list, .answer-item,
.q, .why, .a, .answer-capture, .fill-coverage, .activity-log, .autofill-active,
.fill-where. Question, answer and reason ran together as unstyled paragraphs.

The state vocabulary already exists in the engine (page_answers.py) and in the
protocol (FillItem.flag). This gives it the visual form the rest of the app now
uses: ink = you confirmed it, pencil = the AI drafted it, flag = it needs you.
"""
from __future__ import annotations

import re
from pathlib import Path

CSS = (Path(__file__).resolve().parents[1] / "web" / "static"
       / "styles.css")

# engine state -> the semantic token its row must carry
STATES = {
    "filled": "--ink",
    "drafted": "--pencil",
    "drafting": "--pencil",
    "needs_you": "--flag",
    "refused": "--flag",
}


def _css() -> str:
    return CSS.read_text(encoding="utf-8")


class TestTheReviewListIsBuilt:
    def test_every_previously_unstyled_class_now_exists(self):
        css = _css()
        for name in ("answers-review", "answer-list", "answer-item",
                     "answer-capture", "fill-coverage", "activity-log",
                     "autofill-active", "fill-where", "autofill-activity"):
            assert re.search(r"\." + name + r"\b[^{]*\{", css), (
                f".{name} is used on the Apply Assist screen and defined "
                f"nowhere")

    def test_question_answer_and_reason_are_visually_separated(self):
        """FR-013 — they ran together as three plain paragraphs."""
        css = _css()
        for name in ("q", "why", "a"):
            assert re.search(r"\.answer-item\s+\." + name + r"\b", css), (
                f".answer-item .{name} has no rule, so the question, the "
                f"answer and the reason still read as one block")


class TestStatesCarryTheSharedVocabulary:
    """The engine already distinguishes these five. Until now the screen did
    not, so a field the AI guessed looked exactly like one you confirmed."""

    def test_each_state_is_styled(self):
        css = _css()
        for state in STATES:
            assert f'[data-state="{state}"]' in css, (
                f"state {state!r} has no visual treatment")

    def test_each_state_uses_the_right_semantic_token(self):
        css = _css()
        for state, token in STATES.items():
            block = re.search(
                r'\[data-state="' + state + r'"\][^{]*\{([^}]*)\}', css)
            assert block, f"no rule for {state}"
            assert token in block.group(1), (
                f"{state} should read as {token} — a drafted answer must not "
                f"look like a confirmed one")

    def test_the_states_are_not_all_the_same_colour(self):
        """A vocabulary where every word means the same thing is not a
        vocabulary."""
        assert len(set(STATES.values())) == 3


class TestMotionIsSafeOnBothEngines:
    """Windows renders in WebView2 (Chromium), macOS in WKWebView (WebKit).
    Motion that only one engine understands is motion the other build
    silently loses."""

    def test_no_chromium_only_scroll_driven_animation(self):
        css = _css()
        for feature in ("animation-timeline", "scroll-timeline",
                        "view-timeline"):
            assert feature not in css, (
                f"{feature} is Chromium-only; the macOS build would silently "
                f"render no motion at all")

    def test_every_animation_is_disabled_under_reduced_motion(self):
        css = _css()
        block = re.search(
            r"@media\s*\(prefers-reduced-motion:\s*reduce\)\s*\{(.*?)\n\}",
            css, re.S)
        assert block, "there is no global reduced-motion override"
        body = block.group(1)
        assert "animation-duration" in body and "transition-duration" in body
