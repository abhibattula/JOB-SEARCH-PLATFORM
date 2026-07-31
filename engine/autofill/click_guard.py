"""The submit denylist (feature 011) — the single guarantee that the fill
engine, now allowed to click a field's own widget to set a value, NEVER
clicks a control that submits, applies, advances, saves, finishes, logs in,
registers, creates an account, or pays.

This module is the source of truth. `extension/content/click_guard.js`
mirrors `DENY_TERMS` term-for-term (a parity test in
tests/test_extension_assets.py fails if they drift). Both the Playwright
watcher and the browser companion consult the SAME term set at the moment of
clicking.

Scope (clarify Q1): the verdict is computed from the clicked element's OWN
text/type/role plus the text/type/role of elements it CONTAINS — never its
ancestors. So an option inside a form that also holds a Submit button is
allowed (the Submit is an ancestor), while a real submit button, or a
wrapper that contains one, is refused.
"""
from __future__ import annotations

import re

# Canonical submit-class terms (normalized, lowercase). Mirrored in JS.
# Order-independent; each is matched as a whole-phrase substring of the
# normalized element text.
DENY_TERMS: tuple[str, ...] = (
    "submit",
    "apply",
    "next",
    "continue",
    "save",
    "finish",
    "review and submit",
    "log in",
    "login",
    "sign in",
    "sign up",
    "register",
    "create account",
    "pay",
    "checkout",
    "proceed",
)


# 019 (T062, constitution v1.2.0): the FINAL-class layer. DENY_TERMS keeps
# protecting the fill path unchanged — it still refuses "next"/"continue"
# there, because a filler has no business advancing anything. Progression
# clicks are a separate, narrower permission, and these are the terms that
# permission never extends to. A wizard's Continue is now clickable; the
# Submit at the end of it is not, and never will be.
FINAL_TERMS: tuple[str, ...] = (
    "submit application",
    "submit my application",
    "review and submit",
    "submit",
    "create account",
    "create an account",
    "register",
    "sign up",
    "signup",
    "pay",
    "checkout",
    "place order",
    "confirm and submit",
)


def is_progression_safe(name: str = "") -> bool:
    """True when a control may be clicked to move the application FORWARD.

    False for anything that would submit it, create an account, or pay —
    the three things the human always does themselves (constitution v1.2.0).
    """
    norm = _normalize(name)
    if not norm:
        # An unnamed control is not identifiable as safe; refuse it.
        return False
    for term in FINAL_TERMS:
        if re.search(rf"(?<![a-z]){re.escape(term)}(?![a-z])", norm):
            return False
    return True


def _normalize(text: str) -> str:
    # lowercase, collapse whitespace, strip non-alphanumeric edges so
    # "Continue »" / "  submit  " normalize cleanly
    return re.sub(r"\s+", " ", (text or "").strip().lower())


def is_denylisted(text: str = "", type: str = "", role: str = "") -> bool:
    """True when this element must never be clicked. `text` is the element's
    (self+descendant) visible text; `type` its input/button type; `role` its
    ARIA role."""
    if (type or "").strip().lower() == "submit":
        return True
    norm = _normalize(text)
    if not norm:
        return False
    for term in DENY_TERMS:
        # whole-word/phrase match: the term bounded by non-letters (so
        # "apply" doesn't fire on "applied experience" mid-word, but does on
        # "apply now")
        if re.search(rf"(?<![a-z]){re.escape(term)}(?![a-z])", norm):
            return True
    return False


def is_widget_operable(own_name: str = "", descendant_text: str = "",
                       type_: str = "", role: str = "",
                       descendant_types: list[str] | None = None) -> bool:
    """019 (T036, FR-012): may the filler operate this control to SET A
    VALUE?

    The 011 rule folds descendant text into the verdict, which is right for
    judging a button but wrong for judging a widget: a react-select wrapper
    whose card happens to contain the words "Next" or "Save the date" was
    refused, so an ordinary dropdown became needs_manual. Text is therefore
    judged on the element's OWN accessible name.

    Descendant TYPES are still folded — a wrapper containing a real
    `type=submit` control would submit the form, and that danger is
    unchanged. `is_denylisted` itself is untouched: the fill path's
    button-judging behavior is exactly what it was.
    """
    types = [type_] + list(descendant_types or [])
    if any((t or "").strip().lower() == "submit" for t in types):
        return False
    # An element the page itself declares as an OPTION is a value, not a
    # control: "Next year" in a date menu, "Continue Education" in a
    # dropdown. Its text can therefore never make it submit-class — only a
    # submit type can, and that was refused above. (This is why
    # tests/fixtures/ats_pages/submit_styled_as_option.html exists: a submit
    # button dressed as an option is still caught, by type.)
    if (role or "").strip().lower() == "option":
        return True
    return not is_denylisted(own_name, type_, role)


def combined_signal(own_text: str = "", own_type: str = "", own_role: str = "",
                    descendant_texts: list[str] | None = None,
                    descendant_types: list[str] | None = None,
                    descendant_roles: list[str] | None = None) -> dict:
    """Fold the clicked element's own signal with its DESCENDANTS' (never
    ancestors) into a single {text, type, role} for is_denylisted. If any
    descendant is a submit-type control, the folded type is 'submit'."""
    texts = [own_text] + list(descendant_texts or [])
    types = [own_type] + list(descendant_types or [])
    folded_type = "submit" if any(
        (t or "").strip().lower() == "submit" for t in types
    ) else (own_type or "")
    return {
        "text": " ".join(t for t in texts if t),
        "type": folded_type,
        "role": own_role or "",
    }
