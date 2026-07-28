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

import re
from dataclasses import dataclass

from . import adapters
from . import fields as fields_mod

# Outcomes that permanently settle an element for this job — anything else
# is retried on later scans (e.g. a value may appear after the user
# confirms a drafted answer).
TERMINAL_OUTCOMES = {"filled", "skipped_existing", "no_match", "needs_manual"}

# ---------------------------------------------------------------------------
# 017 (R7, FR-012): an answer may only be written to a field whose SHAPE
# accepts it.
#
# Two defects from the 2026-07-28 live run share this one missing rule. A
# yes/no profile fact was written into four FREE-TEXT work-authorization
# questions that ask for a date, a status, extension options and a
# description; and a paragraph was typed into a custom dropdown because the
# only length guard was keyed on the `custom_combobox` widget flag, which the
# offending element (a search input nested inside the widget) never carried.
#
# Consulted by decide() before emitting a fill AND by drafter._validate
# before accepting a generation, so neither path can write a mis-shaped
# value.
# ---------------------------------------------------------------------------

# Widgets whose answer must be an option, not prose.
_CHOICE_WIDGETS = {"native_select", "custom_combobox", "typeahead"}
_CHOICE_TYPES = {"radio_group", "checkbox_group", "select-one", "select-multiple"}

# When the options are unknown until the widget opens, the answer has to LOOK
# like an option label — the filler fuzzy-matches it against what it harvests.
_MAX_OPTION_WORDS = 4
_MAX_OPTION_CHARS = 60
# Sentence-enders only. A comma does NOT disqualify a label: real option text
# is full of them ("Arlington, TX", "Black or African American, non-Hispanic"),
# and the word budget already rejects run-on answers.
_SENTENCE_PUNCT = re.compile(r"[.!?;]")

# A label that asks for a date, a status, a list or an explanation cannot be
# answered with a bare yes/no token, however yes/no-ish its topic is.
_DESCRIPTIVE_LABEL = re.compile(
    r"when\s+does|expir|what\s+is\s+your|please\s+list|list\s+any|"
    r"provide\s+(additional\s+)?detail|additional\s+detail|please\s+describe|"
    r"describe|explain|please\s+specify|specify|elaborate|"
    r"immigration\s+status|basis\s+of\s+your|which\s+company|how\s+many|"
    r"write\s+out|phonetic",
    re.IGNORECASE,
)

_YES_NO_TOKENS = {"yes", "no", "y", "n", "true", "false"}

_PATH_LIKE = re.compile(r"[\\/]|\.(pdf|docx?|txt|rtf|odt)$", re.IGNORECASE)


def _label_of(descriptor: dict) -> str:
    return " ".join(str(descriptor.get(part) or "") for part in
                    ("label_text", "placeholder", "aria_label", "name", "id"))


def is_choice_control(descriptor: dict) -> bool:
    """True when the field expects one of a fixed set of answers — including
    an input that only reveals its nature through its ancestry (an inner
    search box inside a React-select control)."""
    if descriptor.get("nested_in_choice"):
        return True
    if (descriptor.get("widget") or "") in _CHOICE_WIDGETS:
        return True
    if (descriptor.get("type") or "") in _CHOICE_TYPES:
        return True
    if (descriptor.get("tag") or "").lower() == "select":
        return True
    return bool(descriptor.get("options"))


def _looks_like_an_option_label(text: str) -> bool:
    stripped = text.strip()
    if len(stripped) > _MAX_OPTION_CHARS:
        return False
    if _SENTENCE_PUNCT.search(stripped):
        return False
    return len(stripped.split()) <= _MAX_OPTION_WORDS


def value_fits(descriptor: dict, value) -> tuple[bool, str]:
    """Whether `value` may be written to `descriptor`.

    Returns (True, "") or (False, reason) where reason is one of
    "empty", "wrong_shape", "not_an_option_label", "no_valid_option".
    A refusal leaves the field untouched and flagged — never approximated.
    """
    text = "" if value is None else str(value).strip()
    if not text:
        return False, "empty"

    field_type = (descriptor.get("type") or "").lower()

    # A file input takes a path. Drafted prose reaching set_input_files was a
    # real defect on cover-letter uploads.
    if field_type == "file":
        return (True, "") if _PATH_LIKE.search(text) else (False, "wrong_shape")

    if is_choice_control(descriptor):
        options = [o for o in (descriptor.get("options") or []) if o]
        if options:
            # The options are known: matching decides, not shape. Reject only
            # what cannot possibly be one of them.
            longest = max(len(str(o)) for o in options)
            if len(text) > max(longest * 2, _MAX_OPTION_CHARS):
                return False, "no_valid_option"
            return True, ""
        # Options unknown until the widget opens — the answer must look like
        # a label the filler can match on the page.
        if not _looks_like_an_option_label(text):
            return False, "not_an_option_label"
        return True, ""

    # Free text. A bare yes/no cannot answer a question that asks for a date,
    # a status, a list or an explanation.
    if text.casefold().strip(".") in _YES_NO_TOKENS and \
            _DESCRIPTIVE_LABEL.search(_label_of(descriptor)):
        return False, "wrong_shape"

    return True, ""


def key(descriptor: dict) -> tuple:
    """Ledger key: (per-document token, scan-time stamp)."""
    return (descriptor.get("doc"), descriptor.get("je_idx"))


def settle_entry(outcome: str):
    """016 (T007, R3): the ledger value for a settle. `no_match`/
    `needs_manual` carry the drafter cache epoch — a NEWER answer arriving
    later re-opens the field (the confirm-then-deadlock class); `filled`/
    `skipped_existing` stay plain strings and never retry."""
    if outcome in ("no_match", "needs_manual"):
        from . import drafter

        return (outcome, drafter.cache_version())
    return outcome


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


def name_layout(descriptors: list[dict], ats: str | None = None) -> dict:
    """017 (FR-017): resolve first-vs-full name using the whole document.

    `classify` sees one descriptor at a time, so a lone "Name" box and a
    "Name" box sitting next to "Last name" look identical to it — and the
    live run filled the second kind with the applicant's full name. When a
    document carries a distinct last-name field, a sibling classified
    `full_name` is really the first name.

    Returns {je_idx: tag} overrides; an empty dict means "leave everything
    as classified".
    """
    by_doc: dict = {}
    for descriptor in descriptors:
        tag = adapters.classify(ats, descriptor) or fields_mod.classify(descriptor)
        if tag in ("full_name", "last_name"):
            by_doc.setdefault(descriptor.get("doc"), []).append(
                (descriptor.get("je_idx"), tag))

    overrides: dict = {}
    for entries in by_doc.values():
        tags = {tag for _, tag in entries}
        if "last_name" not in tags or "full_name" not in tags:
            continue
        for je_idx, tag in entries:
            if tag == "full_name":
                overrides[je_idx] = "first_name"
    return overrides


def decide(ats: str | None, descriptor: dict, handled: dict, get_value) -> Decision:
    if not descriptor.get("visible") and (descriptor.get("type") or "") != "file":
        return Decision("ignore")

    entry = handled.get(key(descriptor))
    if entry is not None:
        name = entry[0] if isinstance(entry, tuple) else entry
        if name in TERMINAL_OUTCOMES:
            if isinstance(entry, tuple):
                from . import drafter

                if drafter.cache_version() > entry[1]:
                    pass  # a newer answer exists — re-decide this field
                else:
                    return Decision("skip")
            else:
                return Decision("skip")

    # 017 (FR-017): a document-level override from name_layout wins — it is
    # the only rule that can see more than this one field.
    tag = (descriptor.get("tag_override")
           or adapters.classify(ats, descriptor)
           or fields_mod.classify(descriptor))

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

    # 017 (FR-012): the answer must fit the control. Settling `no_match`
    # leaves the field untouched and epoch-retryable, so a later, correctly
    # shaped answer still gets its chance — the field is never given a value
    # of the wrong shape just because one was available.
    fits, fit_reason = value_fits(descriptor, value)
    if not fits:
        if fit_reason == "empty":
            return Decision("skip")
        return Decision("settle", tag=tag, outcome="no_match")

    if tag == "resume_upload" or (descriptor.get("type") or "") == "file":
        name = str(value).replace("\\", "/").rsplit("/", 1)[-1]
        return Decision("fill", tag=tag, kind="file", value=value, preview=name)

    # 016 (T011/T013, R6): a grouped radio set is ONE logical field — the
    # answer must be one of the member labels; the filler checks that
    # member. Anything unmatched settles no_match (epoch-retryable).
    if (descriptor.get("type") or "") == "radio_group":
        options = descriptor.get("options") or []
        matched = fields_mod.match_option(str(value), options) if options else None
        if matched is None:
            return Decision("settle", tag=tag, outcome="no_match")
        return Decision("fill", tag=tag, kind="radio", value=matched,
                        option_label=matched, preview=matched,
                        ai_draft=isinstance(value, Draft))

    # 017 (C8): a merged checkbox set. The answer must be one of the member
    # labels; the executor ticks THAT member. Checked before the generic
    # options branch, which would otherwise treat the group as a <select>.
    # No new wire kind is introduced — an ordinary kind:"checkbox" item
    # addressed to the member's je_idx — so an older companion cannot
    # mis-fill it and no version gate is needed.
    if (descriptor.get("type") or "") == "checkbox_group":
        options = descriptor.get("options") or []
        matched = fields_mod.match_option(str(value), options) if options \
            else None
        if matched is None:
            return Decision("settle", tag=tag, outcome="no_match")
        return Decision("fill", tag=tag, kind="checkbox", value=True,
                        option_label=matched, preview=matched,
                        ai_draft=isinstance(value, Draft))

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
