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

PROTOCOL_V = 1
MAX_MESSAGE_BYTES = 1_000_000

# Everything the fill engine may report per field. `ai_draft` is 010's
# addition (drafted answer filled + flagged, review pending).
OUTCOMES = ("filled", "skipped_existing", "focused", "not_found",
            "needs_manual")


class ProtocolError(ValueError):
    """Raised for any malformed/oversized/unknown inbound message."""


class _Strict(BaseModel):
    model_config = ConfigDict(extra="ignore")


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

    def as_watcher_dict(self) -> dict:
        return self.model_dump()


class Hello(_Strict):
    secret: str
    version: str
    chrome_version: str = ""


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


_INBOUND: dict[str, type[_Strict]] = {
    "hello": Hello,
    "tab_opened": TabOpened,
    "fields": Fields,
    "fill_result": FillResult,
    "page_event": PageEvent,
    "fill_here": FillHere,
    "pong": Pong,
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
    kind: Literal["text", "select", "checkbox", "file", "secret",
                  "combobox", "typeahead"]
    value: str = ""
    option_label: str | None = None
    file_url: str | None = None
    flag: Literal["ai_draft"] | None = None

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
