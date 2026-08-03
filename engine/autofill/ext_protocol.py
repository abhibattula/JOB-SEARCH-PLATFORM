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
    # 020: "richtext" joins this list for rich-text editors. Adding a widget
    # the model does not know about is NOT a small mistake — pydantic rejects
    # the whole `fields` message, so ONE unknown widget silently stops the
    # entire page from filling. That is exactly what happened while building
    # this feature: the scan was perfect, the tab opened, the watch armed, and
    # nothing filled, with no scan error recorded anywhere.
    widget: Literal["native_select", "custom_combobox", "typeahead",
                    "richtext", ""] = ""
    # 011: Workday's data-automation-id, the stable adapter key ("" if absent)
    automation_id: str = ""
    # 016 (T002, additive — PROTOCOL_V stays 1): grouped-control members
    # (type "radio_group": question = group label, options = member labels,
    # je_idx = FIRST member's) and the required flag. Old serializers omit
    # both; defaults keep their payloads valid.
    members: list[Member] = []
    required: bool = False
    # 021 (FR-008, additive — PROTOCOL_V stays 1): which region of the form
    # this field sits in, and which repeat of that region. `section_label`
    # is "" when UNDETERMINED, which means the app groups flat rather than
    # guessing — a wrong grouping is worse than none. An older companion
    # omits both and behaves exactly as v2.0.0 did.
    section_label: str = ""
    section_index: int = 0
    # 019 (T003, additive — PROTOCOL_V stays 1): which kind of credential
    # form the field sits in, judged by the serializer that can see the form
    # ("login": one password input; "registration": two / create-account
    # context; "": an ordinary field). This is the signal that finally makes
    # the login_email/login_username tags reachable in production.
    form_context: Literal["login", "registration", ""] = ""

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
    # 019 (FR-028, additive): a bot check is present on this page. The
    # escort refuses to advance past one and pauses to the human; nothing
    # is ever clicked on or near it.
    captcha: bool = False


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


class AnswerQuestion(_Strict):
    """017 (D7, FR-045): the applicant typed an answer in the on-page panel
    for a question the system declined to answer. Stored as THEIR answer
    (source 'user', FR-046) so it fills this field now and every future
    application that asks the same thing — and so a purge of AI-written
    answers can never remove it."""
    tab_id: int
    je_idx: str = ""
    question: str
    answer: str


class ApplyHere(_Strict):
    """017 (FR-038): the floating badge's Apply with Apply Assist. The app
    upserts the posting and starts a watched, non-ad-hoc session on THIS tab.
    It starts a fill session and nothing else — no page control is clicked."""
    tab_id: int
    url: str
    title: str = ""
    company: str = ""
    description: str = ""


class SessionControl(_Strict):
    """018 (FR-030/FR-032): stop or advance the fill queue FROM THE PAGE.

    Confers no new capability whatsoever — `stop` and `next` are exactly what
    `POST /api/autofill/stop` and `/next` already do, and the app's own Apply
    Assist page has offered both since 007. This only removes the tab switch:
    stopping a run used to mean leaving the application you were filling.

    Nothing here submits, logs in, or advances a wizard on the page. `next`
    moves the APP's queue to the next job.
    """
    tab_id: int
    action: str  # "stop" | "next"


class CredentialSave(_Strict):
    """019 (FR-017): a login saved from the on-page panel. The password goes
    straight to the OS credential vault and nowhere else; repr masks BOTH the
    secret and the email so no log formatter can leak either."""
    tab_id: int
    domain: str
    email: str
    password: str

    def __repr__(self) -> str:  # pragma: no cover - exercised via tests
        return (f"CredentialSave(tab_id={self.tab_id!r}, "
                f"domain={self.domain!r}, email=•••, password=•••)")

    __str__ = __repr__


class AdvanceResult(_Strict):
    """019 (FR-031): the report channel for EVERY progression click. The
    advancer reports sign_in/next; the opener reports open_apply — one trail,
    one shape. `refused` never retries the same (doc, control_hash)."""
    tab_id: int
    frame_id: int
    kind: Literal["open_apply", "sign_in", "next"]
    status: Literal["clicked", "not_found", "refused"]
    selector_kind: str = ""
    control_hash: str = ""


class AdvanceStep(_Strict):
    """019 (FR-016/FR-023): the ONLY click instruction the engine may issue.
    `open_apply` is deliberately not a valid kind — form-opening stays the
    opener's separate, allowlisted, one-shot job (constitution v1.2.0;
    analyze finding A1). The advancer refuses a second click for a step_key
    it has already acted on."""
    tab_id: int
    frame_id: int
    kind: Literal["sign_in", "next"]
    step_key: str


class PageReport(_Strict):
    """021 (FR-001): the applicant asks for a shareable description of this
    page.

    v2.0.0 met a real Workday application and reported Seen 156 with most
    rows blank, and the suite's two Workday fixtures (9 and 2 fields) could
    not tell us whether that was one scan or an accumulation. This is how the
    question gets answered with evidence rather than a guess.

    `url` is reduced to a bare host before anything is written — a real ATS
    URL routinely carries a session or candidate token in its query string.
    """
    tab_id: int
    frame_id: int
    url: str = ""


_INBOUND: dict[str, type[_Strict]] = {
    "hello": Hello,
    "page_report": PageReport,
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
    "answer_question": AnswerQuestion,
    "apply_here": ApplyHere,
    "session_control": SessionControl,
    "credential_save": CredentialSave,
    "advance_result": AdvanceResult,
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
