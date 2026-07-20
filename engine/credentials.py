"""OS-keychain-backed credential vault for Apply Assist saved logins
(feature 005, spec FR-015-FR-018).

A saved password never touches SQLite — only the OS keychain, via
`keyring`. A tiny "which email is saved for which domain" companion
record lives in the existing `settings` table (`cred_email:{domain}`),
reusing its established small-KV role rather than a new table
(data-model.md). `keyring` does not reliably auto-detect its backend
inside a frozen PyInstaller app (raises "No recommended backend was
available"), so the platform backend is set explicitly when frozen —
mirroring the plyer.platforms.* conditional-hiddenimport pattern already
used elsewhere in this project (research.md §8).
"""
from __future__ import annotations

import sys

import keyring

from . import db, paths

if paths.is_frozen():
    if sys.platform == "win32":
        from keyring.backends import Windows

        keyring.set_keyring(Windows.WinVaultKeyring())
    elif sys.platform == "darwin":
        from keyring.backends import macOS

        keyring.set_keyring(macOS.Keyring())

_SETTING_PREFIX = "cred_email:"


def _setting_key(domain: str) -> str:
    return f"{_SETTING_PREFIX}{domain}"


def save(domain: str, email: str, password: str) -> None:
    keyring.set_password(domain, email, password)
    db.set_setting(_setting_key(domain), email)


def get(domain: str) -> dict | None:
    email = db.get_setting(_setting_key(domain))
    if not email:
        return None
    password = keyring.get_password(domain, email)
    if password is None:
        return None
    return {"email": email, "password": password}


def delete(domain: str) -> None:
    """Clears both the keychain entry and the settings row — leaving either
    behind is a bug (data-model.md invariant): a stray settings row would
    show a domain as "saved" with no retrievable secret; a stray keychain
    entry would leak outside the app's own bookkeeping."""
    email = db.get_setting(_setting_key(domain))
    if email:
        try:
            keyring.delete_password(domain, email)
        except Exception:
            pass
    with db._conn() as conn:
        conn.execute("DELETE FROM settings WHERE key = ?", (_setting_key(domain),))


def list_domains() -> list[dict]:
    """Identifiers only, never secrets — reads only the settings-table
    companion record, never touches the vault."""
    with db._conn() as conn:
        rows = conn.execute(
            "SELECT key, value FROM settings WHERE key LIKE ?",
            (f"{_SETTING_PREFIX}%",),
        ).fetchall()
    return [
        {"domain": row["key"][len(_SETTING_PREFIX):], "email": row["value"]}
        for row in rows
        if row["value"]
    ]
