"""021 (FR-001/FR-002): a shareable, value-free description of one page.

Feature 020 shipped, and the first real Intel Workday application it met came
back Filled 5 / Needs you 149 / Seen 156 — most rows carrying no question at
all. Three causes were readable straight out of the source. One was not: is
156 a single scan genuinely seeing 156 fields, or a stale-frame count summing
forever? The two Workday fixtures in the suite hold 9 and 2 fields, so nothing
in the test suite could answer it, and guessing would have repeated the
mistake this project has already corrected three times by measurement.

So: let the applicant hand back what is actually on the page. Which means the
file has to be safe to hand back.

It records SHAPE, never content. `has_value` is a boolean and that is the
entire signal about anything typed. The URL is reduced to a host, because a
real ATS URL routinely carries a session or candidate token in its query
string — the kind of leak that looks like nothing until it is in a bug report.

Pure by construction: no clock, no filesystem, no `web` import. `captured_at`
is passed in, so the frozen app and the test suite build reports the same way
and the tests need no time freezing.
"""
from __future__ import annotations

from urllib.parse import urlsplit

from .bridge_const import PROTOCOL_V

# The exact key set every field entry carries, always, even when empty. A key
# that appears only when it has content makes two reports from two pages
# impossible to diff — which is the entire point of the file.
_FIELD_KEYS = (
    "tag", "type", "widget", "role",
    "name", "id", "automation_id", "label_text",
    "section_label", "section_index",
    "visible", "required", "has_value",
    "decision", "tag_classified", "reason",
)


def safe_host(url: str | None) -> str:
    """The host of `url`, and nothing else.

    Drops the path, the query string, the fragment, and any `user:pass@`
    credentials — all four of which are places a real application URL puts
    something that must not travel in a shareable file.

    The schemeless branch is not a nicety. `urlsplit("host.com/a?token=x")`
    puts the WHOLE string in `path` and returns an empty netloc, so a caller
    that falls back to the raw value ships the query string. Caught here by
    writing the paired test rather than in a bug report later.
    """
    raw = (url or "").strip()
    try:
        netloc = urlsplit(raw).netloc
    except ValueError:  # malformed IPv6 literal, port out of range
        return ""
    if not netloc:
        # No scheme. Cut at the first path/query/fragment delimiter, then
        # insist the remainder actually looks like a host — otherwise plain
        # prose ("not a url at all") would be echoed back verbatim.
        candidate = raw
        for delimiter in ("/", "?", "#"):
            candidate = candidate.split(delimiter, 1)[0]
        candidate = candidate.strip()
        if not candidate or any(c.isspace() for c in candidate):
            return ""
        if "." not in candidate and ":" not in candidate:
            return ""
        netloc = candidate
    # https://user:pass@host/ is legal and carries a password.
    return netloc.rsplit("@", 1)[-1]


def _field(record: dict) -> dict:
    descriptor = record.get("descriptor") or {}
    # .strip() matters: a control holding only whitespace has not been
    # answered, and reporting it as answered would send the reader hunting
    # for a fill that never happened.
    has_value = bool((descriptor.get("value") or "").strip())
    return {
        "tag": descriptor.get("tag") or "",
        "type": descriptor.get("type") or "",
        "widget": descriptor.get("widget") or "",
        "role": descriptor.get("role") or "",
        "name": descriptor.get("name") or "",
        "id": descriptor.get("id") or "",
        "automation_id": descriptor.get("automation_id") or "",
        "label_text": descriptor.get("label_text") or "",
        "section_label": descriptor.get("section_label") or "",
        "section_index": int(descriptor.get("section_index") or 0),
        "visible": bool(descriptor.get("visible")),
        "required": bool(descriptor.get("required")),
        "has_value": has_value,
        "decision": record.get("decision") or "",
        "tag_classified": record.get("tag") or "",
        "reason": record.get("reason") or "",
    }


def _derive_counts(fields: list[dict]) -> dict:
    sections = {f["section_label"] for f in fields if f["section_label"]}
    return {
        "seen": len(fields),
        "filled": sum(1 for f in fields if f["decision"] == "fill"),
        "needs_you": sum(1 for f in fields if f["decision"] == "skip"),
        "sections": len(sections),
    }


def build(records, *, captured_at: str, app_version: str = "",
          ats: str = "", url_host: str = "", counts: dict | None = None
          ) -> dict:
    """Assemble the report.

    `records` are `{"descriptor": <raw scanner dict>, "decision": str,
    "tag": str, "reason": str}` in document order — exactly what
    `ext_backend._handle_fields` already holds as it walks the page.

    `counts` overrides the derived numbers when the caller has better ones:
    the app's own counters see every frame, and this builder only sees the
    records it was handed.
    """
    fields = [_field(record) for record in records]
    return {
        "captured_at": captured_at,
        "app_version": app_version,
        "protocol_v": PROTOCOL_V,
        "ats": ats,
        # Already reduced by the caller; reduced again here so no caller can
        # leak a full URL through this field by forgetting.
        "url_host": safe_host(url_host) or url_host,
        "counts": dict(counts) if counts else _derive_counts(fields),
        "fields": fields,
    }
