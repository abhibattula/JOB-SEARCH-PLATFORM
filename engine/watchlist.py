"""DB-backed company watchlist (feature 008, FR-015).

companies.yml remains the one-time *seed* source; after seeding, this table
is the single runtime source of monitored boards. User rows and user
toggles must survive app updates: re-seeding only ever inserts slugs the
table has never seen, and never touches `enabled` or `user`-origin rows.
"""
from __future__ import annotations

import json
import sqlite3

from . import db

VALID_ATS = ("greenhouse", "lever", "ashby", "workable", "smartrecruiters", "workday")

# yml keys that live in dedicated columns; everything else (workday host/
# site/search, future per-board config) round-trips through `extra` JSON.
_CORE_KEYS = ("name", "ats", "slug")


def _row_to_dict(row: sqlite3.Row) -> dict:
    return {
        "id": row["id"],
        "ats": row["ats"],
        "slug": row["slug"],
        "name": row["name"],
        "enabled": bool(row["enabled"]),
        "origin": row["origin"],
        "added_at": row["added_at"],
        "last_ok_at": row["last_ok_at"],
        "extra": json.loads(row["extra"]) if row["extra"] else {},
    }


def _entry_slug(entry: dict) -> str:
    # workday entries have no slug in companies.yml — key them by host
    return entry.get("slug") or entry.get("host") or ""


def ensure_seeded() -> int:
    """Insert unknown shipped seeds from companies.yml; returns insert count."""
    from .pipeline import load_companies

    inserted = 0
    entries = load_companies()
    with db._conn() as conn:
        for entry in entries:
            ats = entry.get("ats")
            slug = _entry_slug(entry)
            if ats not in VALID_ATS or not slug:
                continue
            exists = conn.execute(
                "SELECT 1 FROM watchlist WHERE ats = ? AND slug = ?", (ats, slug)
            ).fetchone()
            if exists:
                continue
            extra = {k: v for k, v in entry.items() if k not in _CORE_KEYS}
            conn.execute(
                "INSERT INTO watchlist (ats, slug, name, enabled, origin, added_at,"
                " extra) VALUES (?, ?, ?, 1, 'shipped', ?, ?)",
                (ats, slug, entry.get("name"), db._utcnow(),
                 json.dumps(extra) if extra else None),
            )
            inserted += 1
    return inserted


def list_all() -> list[dict]:
    with db._conn() as conn:
        rows = conn.execute(
            "SELECT * FROM watchlist ORDER BY name COLLATE NOCASE"
        ).fetchall()
    return [_row_to_dict(r) for r in rows]


def add(ats: str, slug: str, name: str | None = None) -> dict:
    if ats not in VALID_ATS:
        raise ValueError(f"unknown ats {ats!r}")
    slug = (slug or "").strip()
    if not slug:
        raise ValueError("slug required")
    with db._conn() as conn:
        try:
            cur = conn.execute(
                "INSERT INTO watchlist (ats, slug, name, enabled, origin, added_at)"
                " VALUES (?, ?, ?, 1, 'user', ?)",
                (ats, slug, name or slug, db._utcnow()),
            )
        except sqlite3.IntegrityError as exc:
            raise ValueError(f"{ats}/{slug} already on the watchlist") from exc
        row = conn.execute(
            "SELECT * FROM watchlist WHERE id = ?", (cur.lastrowid,)
        ).fetchone()
    return _row_to_dict(row)


def set_enabled(entry_id: int, enabled: bool) -> None:
    with db._conn() as conn:
        conn.execute(
            "UPDATE watchlist SET enabled = ? WHERE id = ?",
            (1 if enabled else 0, entry_id),
        )


def remove(entry_id: int) -> str:
    """User rows are deleted outright; shipped rows are disabled instead so a
    later re-seed cannot resurrect a board the user removed (FR-015)."""
    with db._conn() as conn:
        row = conn.execute(
            "SELECT origin FROM watchlist WHERE id = ?", (entry_id,)
        ).fetchone()
        if row is None:
            return "missing"
        if row["origin"] == "user":
            conn.execute("DELETE FROM watchlist WHERE id = ?", (entry_id,))
            return "deleted"
        conn.execute("UPDATE watchlist SET enabled = 0 WHERE id = ?", (entry_id,))
        return "disabled"


def load_active() -> list[dict]:
    """Enabled boards in the companies.yml entry shape the ingest sources
    already consume ({name, ats, slug, **extra})."""
    entries = []
    with db._conn() as conn:
        rows = conn.execute(
            "SELECT * FROM watchlist WHERE enabled = 1 ORDER BY name COLLATE NOCASE"
        ).fetchall()
    for row in rows:
        entry = {"name": row["name"], "ats": row["ats"], "slug": row["slug"]}
        if row["extra"]:
            entry.update(json.loads(row["extra"]))
        entries.append(entry)
    return entries


def mark_ok(ats: str, slug: str) -> None:
    with db._conn() as conn:
        conn.execute(
            "UPDATE watchlist SET last_ok_at = ? WHERE ats = ? AND slug = ?",
            (db._utcnow(), ats, slug),
        )
