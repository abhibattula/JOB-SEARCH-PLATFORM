"""015 (FR-009): bridge protocol constants with ZERO heavy imports.

The companion stamp path (`scripts/stamp_extension.py`) reads PROTOCOL_V and
APP_ID at every app launch. In shipped 1.4.0 it reached them through
`ext_protocol`, whose pydantic import chain failed in the frozen app
(`pydantic_core` missing mid-upgrade) — silently killing pairing. This module
exists so stamping can never again depend on anything beyond the standard
library; an AST allowlist test enforces it stays that way.
`ext_protocol` re-exports these values, so there is exactly one source.
"""

PROTOCOL_V = 1
APP_ID = "jobengine"
