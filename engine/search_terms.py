"""Profile-driven search-term derivation (feature 008, FR-025).

Deterministic — no LLM: target titles first (the resume's own aim), then
experience titles, then a skills-based query. The result is stored on the
profile, shown and editable on the Profile page, and consumed by
jobspy_source; it is derived, reviewed, never silently changed once the
user edits it (derived_from == "user" is sticky).
"""
from __future__ import annotations

MAX_TERMS = 8


def derive(profile: dict | None) -> list[str]:
    profile = profile or {}
    sections = profile.get("resume_sections") or {}
    if not isinstance(sections, dict):
        sections = {}
    terms: list[str] = []
    seen: set[str] = set()

    def add(term: str | None) -> None:
        term = (term or "").strip()
        if not term or term.casefold() in seen or len(terms) >= MAX_TERMS:
            return
        seen.add(term.casefold())
        terms.append(term)

    for title in sections.get("target_titles") or []:
        add(title)
    for entry in sections.get("experience") or []:
        if isinstance(entry, dict):
            add(entry.get("title"))
    skills = [s for s in (profile.get("skills") or []) if isinstance(s, str) and s.strip()]
    if skills:
        add(f"{skills[0]} engineer")
    return terms
