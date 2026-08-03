"""021 (FR-011/FR-012/FR-013): employment and education blocks, answered from
the resume the applicant already uploaded.

`engine/resume_extract.py` has parsed resumes into structured `experience[]`
and `education[]` entries since 008, and `user_profile.resume_sections` has
persisted them ever since. `job_detail.html` renders from them. The fill layer
had never read them — so on a real Workday application every employer, job
title, date, school, degree and GPA came back as "needs you" while the answers
sat in the database.

Selection is by SECTION INDEX: the second work-history block on the page uses
the second stored employment entry. The index comes from the scan
(contracts/section_context.md) and is recomputed every time, never stamped.

The rule that governs everything here, inherited from 017: a missing entry
yields **None**, which means *flag it for the applicant*. Never a guess, never
a fallback to a neighbouring entry, never an empty string typed into a real
employer's form. 017 exists because "Do you have a preferred name?" was filled
with the legal full name by exactly that kind of substitution.

Pure: no I/O, no database, no `web` import. It is handed the profile's stored
sections and returns a string or None.
"""
from __future__ import annotations

_EXPERIENCE: dict[str, str] = {
    "exp_employer": "organization",
    "exp_title": "title",
    "exp_start": "start",
    "exp_end": "end",
    "exp_location": "location",
}

_EDUCATION: dict[str, str] = {
    "edu_school": "institution",
    "edu_degree": "degree",
    "edu_field": "field_of_study",
    "edu_gpa": "gpa",
    "edu_start": "start",
    "edu_end": "end",
}

# The fill layer routes on this set. A tag missing from it falls through to
# the drafter and gets GENERATED instead of read — which is how an employer
# ends up with an invented job title.
HISTORY_TAGS = frozenset(
    set(_EXPERIENCE) | set(_EDUCATION) | {"exp_current"}
)


def _entries(sections, name: str) -> list:
    """The stored list, or [] for anything else `resume_sections` might hold.

    That column is written by a 1.5B model and edited by hand. It has held a
    dict, a list, a bare string and None across versions; none of those may
    raise here, because an exception in the decision loop stops the whole
    page from filling.
    """
    if not isinstance(sections, dict):
        return []
    value = sections.get(name)
    return value if isinstance(value, list) else []


def _entry(sections, name: str, index: int) -> dict | None:
    entries = _entries(sections, name)
    if index < 0 or index >= len(entries):
        # FR-013: past the end is NOT entry 0 and NOT the nearest entry. The
        # applicant is asked. Three work-history blocks against two stored
        # roles must leave the third blank.
        return None
    entry = entries[index]
    return entry if isinstance(entry, dict) else None


def _text(entry: dict | None, field: str) -> str | None:
    if not entry:
        return None
    value = entry.get(field)
    if value is None:
        return None
    # A GPA parsed as a float would otherwise reach a native setter as a
    # non-string and throw inside the filler.
    text = str(value).strip()
    return text or None


def value_for(tag: str | None, section_index: int, sections) -> str | None:
    """The applicant's own history, or None.

    None is a first-class result meaning "we were not told". The caller leaves
    the field alone and flags it. It never means "make something up".
    """
    if not tag:
        return None

    if tag in _EXPERIENCE:
        return _text(_entry(sections, "experience", section_index),
                     _EXPERIENCE[tag])

    if tag == "exp_current":
        entry = _entry(sections, "experience", section_index)
        if entry is None:
            return None
        # Driven by the stored flag, never inferred from a missing end date.
        # An end date the parser failed to read is not evidence that the
        # applicant still works there, and this answer ticks a checkbox on a
        # real application.
        return "Yes" if bool(entry.get("is_current")) else "No"

    if tag in _EDUCATION:
        return _text(_entry(sections, "education", section_index),
                     _EDUCATION[tag])

    return None
