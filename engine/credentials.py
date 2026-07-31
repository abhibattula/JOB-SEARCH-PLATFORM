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
# The default login (006-D): most users reuse the same email/password
# across most job sites, so a single default applies to any domain
# without its own override. A distinct reserved keyring service name and
# settings key — never a real domain string, and deliberately outside the
# cred_email: prefix so it never appears in list_domains()'s per-domain
# override listing.
_DEFAULT_SERVICE = "__default__"
_DEFAULT_SETTING_KEY = "cred_default_email"


def _setting_key(domain: str) -> str:
    return f"{_SETTING_PREFIX}{domain}"


# 019 (T052, FR-021): the alphabet for a generated account password.
# Ambiguous glyphs are excluded because the applicant may have to read one
# back off a screen to a support agent or a phone — O/0, I/l/1, and quote
# characters that shells and forms mangle.
_PW_LOWER = "abcdefghijkmnopqrstuvwxyz"
_PW_UPPER = "ABCDEFGHJKLMNPQRSTUVWXYZ"
_PW_DIGITS = "23456789"
_PW_SYMBOLS = "!@#$%^&*-_=+?"
_PW_ALPHABET = _PW_LOWER + _PW_UPPER + _PW_DIGITS + _PW_SYMBOLS
PASSWORD_LENGTH = 20


def generate_password(length: int = PASSWORD_LENGTH) -> str:
    """A strong password for an account the applicant is creating.

    019 (FR-021): account creation is assisted, not automated — this fills
    the form and is saved to the vault at fill time, and the human presses
    Create account. Guaranteed to contain each class so a site's own
    complexity rule cannot reject it.
    """
    import secrets

    length = max(length, 12)
    required = [secrets.choice(_PW_LOWER), secrets.choice(_PW_UPPER),
                secrets.choice(_PW_DIGITS), secrets.choice(_PW_SYMBOLS)]
    rest = [secrets.choice(_PW_ALPHABET) for _ in range(length - len(required))]
    chars = required + rest
    # Fisher-Yates via secrets so the guaranteed classes are not always at
    # the front (some sites reject a leading symbol).
    for i in range(len(chars) - 1, 0, -1):
        j = secrets.randbelow(i + 1)
        chars[i], chars[j] = chars[j], chars[i]
    return "".join(chars)


def save(domain: str, email: str, password: str) -> None:
    keyring.set_password(domain, email, password)
    db.set_setting(_setting_key(domain), email)


def save_default(email: str, password: str) -> None:
    keyring.set_password(_DEFAULT_SERVICE, email, password)
    db.set_setting(_DEFAULT_SETTING_KEY, email)


def get_default() -> dict | None:
    email = db.get_setting(_DEFAULT_SETTING_KEY)
    if not email:
        return None
    password = keyring.get_password(_DEFAULT_SERVICE, email)
    if password is None:
        return None
    return {"email": email, "password": password}


def delete_default() -> None:
    email = db.get_setting(_DEFAULT_SETTING_KEY)
    if email:
        try:
            keyring.delete_password(_DEFAULT_SERVICE, email)
        except Exception:
            pass
    with db._conn() as conn:
        conn.execute("DELETE FROM settings WHERE key = ?", (_DEFAULT_SETTING_KEY,))


def get(domain: str) -> dict | None:
    """A domain-specific saved login always wins; otherwise falls back to
    the default login (006-D), so most sites work with zero per-domain
    setup — only sites that genuinely use different credentials need an
    explicit override via save()."""
    email = db.get_setting(_setting_key(domain))
    if email:
        password = keyring.get_password(domain, email)
        if password is not None:
            return {"email": email, "password": password}
    return get_default()


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
