"""018 (US3): the answer feed the on-page companion renders.

Through v1.7.0 the panel was fed by `drafter.answers_for_page`, which reads
`drafter._records` — a table that only ever holds questions routed to the AI
drafter. Everything resolved from the profile, the answer bank or a direct tag
map (name, email, phone, location, work authorization, self-ID) never reached
the page. So the surface meant for reviewing an application before submitting
it showed a fraction of that application, and could not show the ordinary
fields at all.

No entry carried a field identifier either, so the panel's Insert and Show me
buttons — both gated on `item.je_idx` — never rendered even once.

This module builds the real index from the decisions themselves. It is pure:
no I/O, no imports from `web/`, no database. The caller
(`ext_backend._handle_fields`) already walks every field and already knows
each one's `je_idx`; it hands what it saw to `build()`.
"""
from __future__ import annotations

import hashlib
import json

GROUPS = ("needs_you", "draft", "profile")
_ORDER = {name: i for i, name in enumerate(GROUPS)}

# Reasons that mean "a person has to answer this", mirrored from the drafter so
# this module stays import-light and testable on its own.
NEEDS_YOU_REASONS = ("sensitive", "no_valid_option", "profile_fact_missing",
                     "attempts_exhausted", "job_budget_exhausted",
                     "cannot_answer", "never_generated", "wrong_shape",
                     "binding_commitment")

# Reasons that will never be retried — the question is closed until the
# applicant answers it themselves.
NEVER_RETRY_REASONS = ("sensitive", "cannot_answer", "never_generated",
                       "binding_commitment")

# 019 (FR-002/FR-017): decision-layer reasons that need no drafter record —
# the fill layer itself knows a person has to look (a stale companion, a
# missing saved login). Not askable: typing an answer fixes neither.
ITEM_NEEDS_YOU_REASONS = ("version_mismatch", "no_saved_login")

# The fields the panel renders. The digest is taken over exactly these, so a
# change the applicant cannot see never causes a re-render.
_RENDERED = ("key", "je_idx", "je_idx_all", "question", "answer", "group",
             "state", "reason", "askable", "section_label", "section_index",
             "profile_field")


def _normalize(question: str) -> str:
    return " ".join((question or "").split()).casefold()


def _profile_field(tag: str | None) -> str:
    """021 (FR-032): the profile field that would answer this question.

    Kept import-light and failure-tolerant — this module is pure and is built
    inside the decision loop, where an exception would stop a page filling.
    """
    try:
        from . import profile_answers

        return profile_answers.profile_field_for(tag) or ""
    except Exception:  # noqa: BLE001
        return ""


def _classify(item: dict, record: dict | None) -> tuple[str, str, bool]:
    """→ (group, state, askable) for one decision."""
    if item.get("action") == "skip":
        if item.get("reason") in ITEM_NEEDS_YOU_REASONS:
            return ("needs_you", "needs_you", False)
        if record is None:
            # A field we deliberately ignored is not an unanswered question.
            # Listing it would bury the ones that genuinely need an answer.
            return ("", "", False)
        reason = record.get("reason")
        if record.get("state") == "failed" and reason in NEEDS_YOU_REASONS:
            state = "refused" if reason in NEVER_RETRY_REASONS else "needs_you"
            return ("needs_you", state, True)
        if record.get("state") == "done":
            return ("draft", "drafted", False)
        return ("draft", "drafting", False)
    if item.get("ai_draft"):
        return ("draft", "drafted", False)
    return ("profile", "filled", False)


def build(entries, drafter_records=None) -> list[dict]:
    """Assemble the feed for one job.

    `entries` are the decisions `_handle_fields` made, in document order.
    `drafter_records` maps a normalized question to the drafter's record, so a
    skipped field can say WHY it was skipped.

    Keyed: a field seen twice in one pass (or across the scans of one page)
    appears once, carrying the latest decision. That is the difference between
    a review list and the 170-row flood 017 had to clean up.
    """
    records = {}
    for question, rec in (drafter_records or {}).items():
        records[_normalize(question)] = rec

    ordered: list[tuple] = []
    by_key: dict[tuple, dict] = {}

    for item in entries:
        # FR-037: a secret is fill-and-forget. It goes into the field and is
        # never rendered, logged or sent back.
        if item.get("secret"):
            continue
        question = item.get("question") or ""
        record = records.get(_normalize(question))
        group, state, askable = _classify(item, record)
        if not group:
            continue
        answer = item.get("answer") or ""
        if not answer and record is not None:
            answer = record.get("answer") or ""
        section_label = item.get("section_label") or ""
        section_index = int(item.get("section_index") or 0)
        je_idx = item.get("je_idx") or ""
        # 021 (FR-004/FR-010): the key is the QUESTION within its section, not
        # the element. A Workday prompt is a button plus its listbox and
        # FIELD_SELECTOR matches both, so keying on (doc, je_idx) — as v2.0.0
        # did — made every dropdown two identical rows. Scoping to the section
        # is what keeps this safe: two employment blocks both asking "From"
        # are two real questions, and merging them would be worse than the
        # flood it fixes.
        key = (section_label, section_index, _normalize(question))
        existing = by_key.get(key)
        if existing is None:
            ordered.append(key)
            by_key[key] = {
                # The stable ledger key of the first element, kept because the
                # panel uses it as a row identity across scans.
                "key": item.get("key") or question,
                "je_idx": je_idx,
                # FR-005: every element behind this row, so "Show me" can
                # reach each one. `je_idx` STAYS A STRING — panel.js uses it
                # as one in five places and it feeds the render digest.
                "je_idx_all": [je_idx] if je_idx else [],
                "question": question,
                "answer": answer,
                "group": group,
                "state": state,
                "reason": item.get("reason")
                          or (record.get("reason") if record else None),
                "askable": askable,
                "section_label": section_label,
                "section_index": section_index,
                # 021 (FR-032): "Add it to your profile and it fills
                # automatically next time" was a dead instruction — it never
                # said WHICH field. On the applicant's real page it appeared
                # on Country/Region and State, both of which the app already
                # knows about and they had simply not filled in.
                "profile_field": _profile_field(item.get("tag")),
            }
            continue
        if je_idx and je_idx not in existing["je_idx_all"]:
            existing["je_idx_all"].append(je_idx)
        # An answerless later decision never displaces one that carries a
        # value — what the applicant needs to review is precisely the value
        # we put there (the v1.8.0 rule, preserved through collapsing).
        if not answer and existing["answer"]:
            continue
        existing.update({
            "key": item.get("key") or existing["key"],
            "je_idx": existing["je_idx"] or je_idx,
            "question": question or existing["question"],
            "answer": answer or existing["answer"],
            "group": group,
            "state": state,
            "reason": item.get("reason")
                      or (record.get("reason") if record else None),
            "askable": askable,
        })

    items = [by_key[k] for k in ordered]
    # needs-you first: it is the only group with anything to do in it.
    items.sort(key=lambda i: _ORDER[i["group"]])
    return items


def counts(items) -> dict:
    """How many of each group — what the companion's group headers show."""
    out = {name: 0 for name in GROUPS}
    for item in items:
        out[item["group"]] += 1
    return out


def digest(items) -> str:
    """A stable fingerprint of the rendered feed.

    FR-027: the app pushed this payload on EVERY scan — up to 400 KB every two
    seconds, and every push rebuilt the whole panel, which is what destroyed
    half-typed answers. With a digest, an unchanged scan sends nothing.
    """
    canonical = [[item.get(field) for field in _RENDERED] for item in items]
    blob = json.dumps(canonical, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()
