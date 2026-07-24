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
