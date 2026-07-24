"""Transport-agnostic per-field fill decisions (feature 010, T004).

Extracted verbatim from watcher._process_field so the Playwright watcher
and the extension backend share ONE implementation of the safety-critical
rules:

- a non-empty field is sacred (the user's own input above all);
- a focused field is never touched;
- terminal ledger entries are never retried;
- option selects only fill on an explicit label match;
- password previews are masked at decision time.

This module DECIDES; it never touches a browser. Executors (watcher.py via
Playwright locators, ext_backend.py via bridge FillItems) apply the
decision and record the eventual outcome.
"""
from __future__ import annotations

from dataclasses import dataclass

from . import adapters
from . import fields as fields_mod

# Outcomes that permanently settle an element for this job — anything else
# is retried on later scans (e.g. a value may appear after the user
# confirms a drafted answer).
TERMINAL_OUTCOMES = {"filled", "skipped_existing", "no_match", "needs_manual"}


def key(descriptor: dict) -> tuple:
    """Ledger key: (per-document token, scan-time stamp)."""
    return (descriptor.get("doc"), descriptor.get("je_idx"))


class Draft(str):
    """A value that is an AI draft, not a settled fact. get_value may return
    one; decide() then flags the fill as ai_draft (filled + flagged for
    review) rather than a plain fill. Subclasses str so every existing
    value path treats it as text transparently."""
    __slots__ = ()


@dataclass
class Decision:
    """What to do with one serialized field.

    action:
      "ignore" — not a fillable sighting (invisible non-file); not counted
      "skip"   — counted as seen, nothing to do this scan
      "settle" — record `outcome` now (no browser action)
      "fill"   — perform `kind` with `value`; on success record "filled"
                 with `preview`
    """
    action: str
    tag: str = ""
    outcome: str = ""
    kind: str = ""  # text | select | checkbox | file
    value: object = None
    option_label: str | None = None
    preview: str = ""
    secret: bool = False
    ai_draft: bool = False


def decide(ats: str | None, descriptor: dict, handled: dict, get_value) -> Decision:
    if not descriptor.get("visible") and (descriptor.get("type") or "") != "file":
        return Decision("ignore")

    if handled.get(key(descriptor)) in TERMINAL_OUTCOMES:
        return Decision("skip")

    tag = adapters.classify(ats, descriptor) or fields_mod.classify(descriptor)

    # A value already present is sacred — the user's own input above all.
    if (descriptor.get("value") or "").strip():
        if tag != "free_text_unknown":
            return Decision("settle", tag=tag, outcome="skipped_existing")
        return Decision("skip")
    if descriptor.get("focused"):
        return Decision("skip")  # never touch the field the user is typing in

    value = get_value(tag, descriptor)
    if value is None:
        return Decision("skip")

    if tag == "resume_upload" or (descriptor.get("type") or "") == "file":
        name = str(value).replace("\\", "/").rsplit("/", 1)[-1]
        return Decision("fill", tag=tag, kind="file", value=value, preview=name)

    # 011: widget-aware option handling. A typeahead types then picks a
    # suggestion; a custom combobox is opened and an option clicked; a native
    # <select> keeps its exact prior path. Non-combobox descriptors that
    # merely carry options are treated as native selects (unchanged).
    widget = descriptor.get("widget") or ""
    if widget == "typeahead":
        return Decision("fill", tag=tag, kind="typeahead", value=str(value),
                        option_label=str(value), preview=str(value))
    if widget == "custom_combobox" or descriptor.get("options"):
        options = descriptor.get("options")
        if options:
            matched = fields_mod.match_option(str(value), options)
            if matched is None:
                return Decision("settle", tag=tag, outcome="no_match")
            label = matched
        else:
            # custom combobox whose options aren't readable until opened:
            # pick by the value's own text (the filler matches visible text)
            label = str(value)
        kind = "combobox" if widget == "custom_combobox" else "select"
        return Decision("fill", tag=tag, kind=kind, value=value,
                        option_label=label, preview=label)

    if (descriptor.get("type") or "") == "checkbox":
        if not value:
            return Decision("skip")
        return Decision("fill", tag=tag, kind="checkbox", value=True,
                        preview=str(value))

    secret = tag == "login_password"
    is_draft = isinstance(value, Draft)
    return Decision("fill", tag=tag, kind="text", value=str(value),
                    preview="•••" if secret else str(value), secret=secret,
                    ai_draft=is_draft)
