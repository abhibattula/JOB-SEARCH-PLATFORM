"""Bridge message schemas (feature 010) — the single trust boundary
between the app and the browser companion. Everything the extension sends
is untrusted input: strict pydantic validation, hard size bound, unknown
types rejected. extension/background/protocol.js mirrors the names; THIS
file is authoritative.
"""
from __future__ import annotations

import itertools
import json
import threading
from typing import Literal

from pydantic import BaseModel, ConfigDict, ValidationError

# 015 (FR-009): the constants live in the dependency-free bridge_const module
# (the stamp path reads them without touching pydantic); re-exported here so
# existing consumers keep one authoritative name.
from .bridge_const import PROTOCOL_V  # noqa: F401  (re-export)

MAX_MESSAGE_BYTES = 1_000_000

# Everything the fill engine may report per field. `ai_draft` is 010's
# addition (drafted answer filled + flagged, review pending).
OUTCOMES = ("filled", "skipped_existing", "focused", "not_found",
            "needs_manual")


class ProtocolError(ValueError):
    """Raised for any malformed/oversized/unknown inbound message."""


class _Strict(BaseModel):
    model_config = ConfigDict(extra="ignore")


class Member(_Strict):
    """016: one element of a grouped control (radio group member)."""
    je_idx: str
    label: str = ""


class Descriptor(_Strict):
    """One form field as serialized by content/scanner.js — the exact
    shape watcher.py's SERIALIZE_JS produces, so fields.py + adapters.py
    classify either backend's output unchanged."""
    je_idx: str
    doc: str
    tag: str
    type: str = ""
    name: str = ""
    id: str = ""
    label_text: str = ""
    placeholder: str = ""
    aria_label: str = ""
    autocomplete: str = ""
    value: str = ""
    options: list[str] = []
    maxlength: int | None = None
    focused: bool = False
    visible: bool = True
    # 011: how the field is operated (drives the fill technique). "" = a
    # plain input handled by the text/checkbox/file paths.
    widget: Literal["native_select", "custom_combobox", "typeahead", ""] = ""
    # 011: Workday's data-automation-id, the stable adapter key ("" if absent)
    automation_id: str = ""
    # 016 (T002, additive — PROTOCOL_V stays 1): grouped-control members
    # (type "radio_group": question = group label, options = member labels,
    # je_idx = FIRST member's) and the required flag. Old serializers omit
    # both; defaults keep their payloads valid.
    members: list[Member] = []
    required: bool = False

    def as_watcher_dict(self) -> dict:
        return self.model_dump()


class Hello(_Strict):
    secret: str
    version: str
    chrome_version: str = ""
    # 015 (T009, additive — PROTOCOL_V stays 1): which browser the companion
    # runs in ("chrome" | "edge" | "" unknown), detected from the UA string.
    browser: str = ""


class TabOpened(_Strict):
    req_id: str
    tab_id: int


class Fields(_Strict):
    tab_id: int
    frame_id: int
    url: str
    doc: str
    descriptors: list[Descriptor]


class OutcomeItem(_Strict):
    je_idx: str
    outcome: Literal[OUTCOMES]  # type: ignore[valid-type]
    detail: str = ""


class FillResult(_Strict):
    tab_id: int
    frame_id: int
    items: list[OutcomeItem]


class PageEvent(_Strict):
    tab_id: int
    kind: Literal["nav", "tab_closed", "frame_gone", "submit_detected"]
    url: str = ""


class FillHere(_Strict):
    tab_id: int
    url: str
    title: str = ""


class Pong(_Strict):
    pass


class ScoreRequest(_Strict):
    """012: a job posting the user is browsing, to be scored on demand. The
    discovery content script sends this; `tab_id` is stamped by the SW. The
    fill session is never involved."""
    tab_id: int
    url: str
    title: str = ""
    company: str = ""
    description: str = ""


class SaveJob(_Strict):
    """012: save the browsed posting into the feed/tracker (source=manual)."""
    tab_id: int
    url: str
    title: str = ""
    company: str = ""
    description: str = ""
    location: str = ""


class ScanError(_Strict):
    """016: a content-script scan exception, reported instead of swallowed
    (doctor counts these; message is truncated app-side, never page
    content)."""
    tab_id: int
    message: str = ""


class ChildTab(_Strict):
    """016: a tab opened FROM the watched tab (openerTabId match) — the
    watch transfers to it (new-tab Apply flows)."""
    tab_id: int
    opener_tab_id: int


class FillAgain(_Strict):
    """016: the on-page panel's Fill again — app clears retryable ledger
    entries, resets draft backoff for the page, then nudges a rescan."""
    tab_id: int


_INBOUND: dict[str, type[_Strict]] = {
    "hello": Hello,
    "tab_opened": TabOpened,
    "fields": Fields,
    "fill_result": FillResult,
    "page_event": PageEvent,
    "fill_here": FillHere,
    "pong": Pong,
    "score_request": ScoreRequest,
    "save_job": SaveJob,
    "scan_error": ScanError,
    "child_tab": ChildTab,
    "fill_again": FillAgain,
}


def parse_inbound(raw: str | bytes):
    if len(raw) > MAX_MESSAGE_BYTES:
        raise ProtocolError(f"message exceeds {MAX_MESSAGE_BYTES} bytes")
    try:
        data = json.loads(raw)
    except (TypeError, ValueError) as exc:
        raise ProtocolError(f"not valid JSON: {exc}") from exc
    if not isinstance(data, dict) or data.get("v") != PROTOCOL_V:
        raise ProtocolError("missing/unsupported protocol version")
    model = _INBOUND.get(data.get("type", ""))
    if model is None:
        raise ProtocolError(f"unknown message type {data.get('type')!r}")
    try:
        return model.model_validate(data)
    except ValidationError as exc:
        raise ProtocolError(str(exc)) from exc


class FillItem(_Strict):
    """One field-level instruction (app → extension). `secret` values are
    fill-and-forget on the extension side; masked here in repr so a log
    formatter can never leak them."""
    je_idx: str
    # 016: "radio" checks the member whose label is `value` (version-gated
    # app-side — never sent to a pre-016 companion).
    kind: Literal["text", "select", "checkbox", "file", "secret",
                  "combobox", "typeahead", "radio"]
    value: str = ""
    option_label: str | None = None
    file_url: str | None = None
    # 017 (FR-031, additive — PROTOCOL_V stays 1): the file's REAL name and
    # expected type. attachFile used to read a `data-je-filename` attribute
    # that nothing ever wrote, so every upload arrived as "resume.pdf"; and
    # with no expected type there was nothing to verify the bytes against.
    # Older companions ignore both fields.
    filename: str | None = None
    mime: str | None = None
    # 016: "needs_you" marks an unfilled field for the on-page highlight.
    flag: Literal["ai_draft", "needs_you"] | None = None

    def __repr__(self) -> str:  # pragma: no cover - exercised via tests
        shown = "•••" if self.kind == "secret" else self.value
        return (f"FillItem(je_idx={self.je_idx!r}, kind={self.kind!r}, "
                f"value={shown!r}, flag={self.flag!r})")

    __str__ = __repr__


_seq = itertools.count(1)
_seq_lock = threading.Lock()


def outbound(type_: str, **payload) -> dict:
    """Build a versioned envelope for app→extension messages."""
    with _seq_lock:
        seq = next(_seq)
    return {"v": PROTOCOL_V, "type": type_, "seq": seq, **payload}
