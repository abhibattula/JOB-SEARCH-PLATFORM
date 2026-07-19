"""User-configurable settings, stored in the database so packaged-app users
never edit files. Read precedence: environment variable (developer override)
→ settings table → built-in default.
"""
from __future__ import annotations

import os

from . import db

DEFAULTS = {
    "LLM_API_KEY": "",
    "LLM_BASE_URL": "https://api.groq.com/openai/v1",
    "LLM_MODEL": "llama-3.3-70b-versatile",
    "JOBSPY_LINKEDIN": "0",
    "SCHEDULE_REFRESH": "0",
    "MAX_SCORE_PER_RUN": "150",
    "ALERTS_ENABLED": "1",
    "UPDATE_CHECK": "1",
}


def get(name: str, default: str | None = None) -> str | None:
    env = os.environ.get(name)
    if env is not None and env != "":
        return env
    stored = db.get_setting(name)
    if stored is not None and stored != "":
        return stored
    return DEFAULTS.get(name, default)


def set(name: str, value: str) -> None:  # noqa: A001 - deliberate API name
    db.set_setting(name, value)


def mask_key(key: str) -> str:
    if not key:
        return ""
    if len(key) <= 8:
        return "*" * len(key)
    return f"{key[:4]}…{key[-4:]}"
