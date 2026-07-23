"""CI gate (008 FR-031): the version string lives in three places — the git
tag, packaging/windows.iss, and engine.APP_VERSION. They drifted silently
before (audit finding); this fails the build loudly when they disagree.

Usage: python packaging/check_version.py   (reads GITHUB_REF_NAME when set)
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import APP_VERSION  # noqa: E402


def main() -> int:
    iss_text = (ROOT / "packaging" / "windows.iss").read_text(encoding="utf-8")
    match = re.search(r'#define MyAppVersion "([^"]+)"', iss_text)
    iss_version = match.group(1) if match else "(missing)"
    tag = os.environ.get("GITHUB_REF_NAME", "")

    errors = []
    if iss_version != APP_VERSION:
        errors.append(
            f"windows.iss says {iss_version} but engine.APP_VERSION is {APP_VERSION}"
        )
    if tag.startswith("v") and tag.lstrip("v") != APP_VERSION:
        errors.append(f"git tag {tag} does not match engine.APP_VERSION {APP_VERSION}")

    if errors:
        for error in errors:
            print(f"FAIL: {error}", file=sys.stderr)
        return 1
    print(f"OK: version {APP_VERSION} consistent (tag={tag or 'n/a'})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
