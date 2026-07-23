"""Background profile import from the uploaded resume (feature 009, US3).

Root causes fixed here: extraction used to run synchronously inside the
upload request (the window froze for minutes with zero feedback), and its
results were applied fill-only-blank — invisible on an already-complete
profile. Now: extraction runs on a daemon thread behind the same
state-machine pattern as engine/updates.py, with stage/chunk progress the
UI polls; the result is a PROPOSAL listing every field as
current-vs-from-resume; nothing changes until the user applies their
choices on the review screen (FR-012/FR-014/FR-015).

Visa/work-authorization fields are deliberately never part of a proposal.
The proposal is session-scoped (an app restart drops it — re-import is one
click), matching the Apply Assist queue and updates.py.
"""
from __future__ import annotations

import logging
import threading

from . import db

log = logging.getLogger(__name__)

IDENTITY_FIELDS = ("first_name", "last_name", "email", "phone",
                   "linkedin_url", "portfolio_url")
LIST_FIELDS = ("skills", "target_titles", "target_locations")

_lock = threading.Lock()
_state: dict = {}
_thread: threading.Thread | None = None


def reset_state() -> None:
    with _lock:
        _state.clear()
        _state.update({
            "state": "idle", "stage": None, "chunk_done": 0, "chunk_total": 0,
            "error": None, "proposal": None, "started_at": None,
        })


reset_state()


def status() -> dict:
    with _lock:
        return {key: _state[key] for key in
                ("state", "stage", "chunk_done", "chunk_total", "error")}


def proposal() -> dict | None:
    with _lock:
        return _state["proposal"]


def start_import(background: bool = True) -> bool:
    """Kick off extraction. False when already running or no resume is on
    file. `background=False` runs inline (tests, CLI)."""
    profile = db.get_profile() or {}
    if not profile.get("resume_text"):
        return False
    with _lock:
        if _state["state"] == "extracting":
            return False
        _state.update(state="extracting", stage="contact", chunk_done=0,
                      chunk_total=0, error=None, proposal=None,
                      started_at=db._utcnow())
    if background:
        global _thread
        _thread = threading.Thread(target=_run_import, daemon=True)
        _thread.start()
    else:
        _run_import()
    return True


def join_for_tests(timeout: float = 10.0) -> None:
    """Wait for a background import to finish. Tests MUST call this before
    their monkeypatches unwind — a leaked thread that outlives its stubs
    sees the real local model and runs minutes of real inference."""
    thread = _thread
    if thread is not None and thread.is_alive():
        thread.join(timeout)


def _run_import() -> None:
    from . import matcher, resume_extract

    try:
        profile = db.get_profile() or {}
        text = profile.get("resume_text") or ""

        with _lock:
            _state["stage"] = "contact"
        regex_contact = resume_extract.extract_contact(text)

        with _lock:
            _state["stage"] = "skills"
        try:
            extracted_skills = matcher.extract_skills(text)
        except Exception:
            log.warning("skill extraction failed", exc_info=True)
            extracted_skills = []

        with _lock:
            _state["stage"] = "sections"

        def on_progress(done: int, total: int) -> None:
            with _lock:
                _state["chunk_done"] = done
                _state["chunk_total"] = total

        sections = resume_extract.extract(text, on_progress=on_progress)

        built = _build_proposal(profile, sections, regex_contact, extracted_skills)
        with _lock:
            _state.update(state="ready", proposal=built, error=None)
    except Exception as exc:
        log.warning("profile import failed", exc_info=True)
        with _lock:
            _state.update(state="failed", error=str(exc)[:300])


def _tier() -> str:
    from . import matcher

    return matcher.scoring_tier()


def _sections_summary(sections_dict: dict | None) -> dict:
    sections_dict = sections_dict or {}
    return {
        "experience": len(sections_dict.get("experience") or []),
        "education": len(sections_dict.get("education") or []),
        "projects": len(sections_dict.get("projects") or []),
        "skills": len(sections_dict.get("skills") or []),
    }


def _build_proposal(profile: dict, sections, regex_contact,
                    extracted_skills: list[str]) -> dict:
    """Every field, current vs from-resume, with the spec defaults:
    blank→apply, conflict→keep, identical→none, lists→merge,
    user-edited sections→keep (with the edit timestamp as a warning)."""
    contact = sections.contact if sections and sections.contact else None
    fields: list[dict] = []

    def contact_value(name: str) -> str:
        for source in (contact, regex_contact):
            if source is not None:
                value = (getattr(source, name, "") or "").strip()
                if value:
                    return value
        return ""

    for name in IDENTITY_FIELDS:
        current = (profile.get(name) or "").strip()
        proposed = contact_value(name)
        if not proposed:
            default = "none"
        elif not current:
            default = "apply"
        elif current == proposed:
            default = "none"
        else:
            default = "keep"
        fields.append({"field": name, "kind": "text",
                       "current": current, "proposed": proposed,
                       "default": default})

    # list fields — merge-by-default
    proposed_lists = {
        "skills": list(dict.fromkeys(
            (sections.skills if sections else []) + (extracted_skills or [])
        )),
        "target_titles": list(sections.target_titles) if sections else [],
        "target_locations": (
            [contact_value("location")] if contact_value("location") else []
        ),
    }
    for name in LIST_FIELDS:
        current = list(profile.get(name) or [])
        proposed = proposed_lists.get(name) or []
        current_fold = {v.casefold() for v in current}
        new_items = [v for v in proposed if v.casefold() not in current_fold]
        if not proposed or not new_items:
            default = "none" if not new_items else "merge"
        elif not current:
            default = "apply"
        else:
            default = "merge"
        if not proposed:
            default = "none"
        fields.append({"field": name, "kind": "list",
                       "current": current, "proposed": proposed,
                       "default": default})

    sections_dict = sections.model_dump() if sections else None
    current_sections = profile.get("resume_sections")
    edited_at = profile.get("sections_edited_at")
    if not sections_dict or not any(_sections_summary(sections_dict).values()):
        sections_default = "none"
    elif edited_at:
        sections_default = "keep"
    elif not current_sections:
        sections_default = "apply"
    else:
        sections_default = "apply"
    fields.append({
        "field": "resume_sections", "kind": "sections",
        "current_summary": _sections_summary(current_sections),
        "proposed_summary": _sections_summary(sections_dict),
        "proposed_sections": sections_dict,
        "edited_at": edited_at,
        "default": sections_default,
    })

    has_differences = any(f["default"] != "none" for f in fields)
    return {
        "generated_at": db._utcnow(),
        "resume_filename": profile.get("resume_filename"),
        "tier": _tier(),
        "has_differences": has_differences,
        "fields": fields,
    }


def apply_import(decisions: dict[str, str]) -> dict:
    """Apply the user's per-field choices in one save. 'apply' adopts the
    resume value; 'merge' unions lists; 'keep'/absent leaves the user's
    value. Applying resume_sections IS the explicit consent that clears
    the sections_edited_at protection. Consumes the proposal."""
    with _lock:
        built = _state["proposal"]
    if built is None:
        raise RuntimeError("no import proposal is ready — run an import first")

    profile = db.get_profile() or {}
    updates: dict = {}
    applied: list[str] = []

    for field in built["fields"]:
        name = field["field"]
        decision = decisions.get(name, "keep")
        if decision not in ("apply", "merge"):
            continue
        if field["kind"] == "text":
            if field["proposed"]:
                updates[name] = field["proposed"]
                applied.append(name)
        elif field["kind"] == "list":
            proposed = field["proposed"] or []
            if decision == "merge":
                current = list(profile.get(name) or [])
                fold = {v.casefold() for v in current}
                merged = current + [v for v in proposed if v.casefold() not in fold]
                updates[name] = merged
            else:
                updates[name] = proposed
            applied.append(name)
        elif field["kind"] == "sections":
            if field.get("proposed_sections"):
                updates["resume_sections"] = field["proposed_sections"]
                updates["sections_edited_at"] = None  # applying = consent
                applied.append(name)

    if updates:
        db.save_profile(**updates)

    # FR-015: refresh derived search terms unless the user owns them
    stored_terms = (db.get_profile() or {}).get("search_terms") or {}
    if not (isinstance(stored_terms, dict) and stored_terms.get("derived_from") == "user"):
        from . import search_terms as search_terms_mod

        derived = search_terms_mod.derive(db.get_profile() or {})
        if derived:
            db.save_profile(search_terms={
                "terms": derived, "derived_from": "resume",
                "updated_at": db._utcnow(),
            })

    with _lock:
        _state.update(state="applied", proposal=None)
    return {"applied": applied}
