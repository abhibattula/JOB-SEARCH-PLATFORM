# Phase 1 Data Model — 022 The Case File

This feature is presentational, so its "data model" is mostly a vocabulary
contract rather than new storage. Two preference rows are the only persisted
additions, and both use the existing key/value store.

## 1. Design token

A named value with a light and a dark binding. Declared once in the stylesheet's
`:root` and `[data-theme="dark"]` blocks and, for the browser panel, injected
into its shadow root (it cannot inherit through `all:initial`).

### Semantic colour tokens (the nine)

| Token | Light | Dark | Meaning |
|---|---|---|---|
| `--paper` | `#f6f7f5` | `#12160f` | page background |
| `--leaf` | `#ffffff` | `#1a1f18` | card / raised surface |
| `--ink` | `#12211c` | `#dfe6dd` | text; **a fact the applicant confirmed** |
| `--ink-soft` | `#4a5b53` | `#9aa89e` | secondary text |
| `--rule` | `#dfe4e0` | `#2b332a` | hairlines, dividers |
| `--seal` | `#1f6f5c` | `#4fc4a1` | action, current, done |
| `--pencil` | `#4a5f7a` | `#8fa8c4` | **provisional — drafted, not confirmed** |
| `--flag` | `#b8792a` | `#e0a53c` | **needs the applicant** |
| `--stop` | `#a63a2e` | `#ef7367` | rejected, failed, destructive |

Each carries a `-tint` companion for fills. Dark values are indicative; the
binding constraint is FR-005 (every pairing meets WCAG AA in both themes), and
the test reads the real values out of the stylesheet rather than this table.

### Non-colour tokens

Type scale, spacing steps, radii, elevation and motion durations carry forward
from the existing block (`styles.css:39-67`) with values retuned to the new type.
`--mono` narrows in *usage*, not definition: FR-008 restricts it to
machine-produced values.

### Retired tokens

`--accent`, `--ok`, `--warn`, `--danger`, `--draft`, `--surface*`, `--line*`,
`--on-emphasis` are replaced by the nine above. Two tokens that were *referenced
but never defined* — `--bg` and `--border` (`styles.css:563-564`) — are removed
along with the bug they caused (R10).

## 2. Semantic state

The product's existing meaning, given one visual form. **Not invented for this
feature**: `FillItem.flag` already carries it (`ext_protocol.py:348`).

| State | Protocol value | Token | Applies to |
|---|---|---|---|
| confirmed | *(no flag)* | `--ink` | a field filled from the profile; a fact the applicant entered |
| drafted | `"ai_draft"` | `--pencil` | an AI-written answer awaiting review; untailored generated text |
| needs-you | `"needs_you"` | `--flag` | a field left for the applicant; a container asking for review |
| done | — | `--seal` | a completed step, a current selection, a primary action |

**Nesting rule**: a container that needs the applicant is flagged; provisional
content *inside* it is pencil. The container asks; the marks describe.

## 3. Provenance

How a match score was produced. Read from `match_json.method`, surfaced by
`engine/db.py:635` as `match_method`. Values verified in R2.

| `match_method` | Written at | Stamp | Text for assistive tech |
|---|---|---|---|
| `"basic"` | `pipeline.py:270` | pencil, dashed ring | "keyword match" |
| `"local"` | `upgrade.py:288` | ink, solid ring | "scored on this computer" |
| `"llm"` | `upgrade.py:288` | sealed, double ring | "full analysis" |
| absent | — | empty outline | "not scored yet" |

**Invariant**: the treatment is a pure function of `match_method`. No screen may
derive it from anything else, so the four surfaces cannot disagree.

**Not a state transition**: a score can move `basic → local → llm` as the
background pass upgrades it, but the stamp only ever reflects the current stored
value. Nothing tracks or animates the transition.

## 4. Feed fingerprint

A value derived from what is currently rendered, used to decide whether a
refresh needs to change anything (R4). Not persisted — computed per request.

**Input, in row order:**

| Field | Why it is in the hash |
|---|---|
| `id` | identity and ordering |
| `status` | drives saved/applied/hidden flags |
| `stage` | pipeline dropdown value |
| `match_score` | the number shown |
| `match_method` | the stamp treatment |
| `is_new` | the "new" flag and row tint |
| `delisted` | the delisted badge |
| `follow_up` | the follow-up flag |
| `notes` rendered summary | the pipeline view shows either "✎ notes" or the first 18 characters, so the *displayed* summary — not a presence flag, and not the full text — is what must be hashed |

**Plus context:** `total`, `page`, and the query signature.

**The rule**: everything the applicant can see is hashed; nothing they cannot is.
A presence-only flag would have been wrong here — editing a note from "call
back" to "sent email" changes the visible summary while presence stays true, and
the row would never refresh. Full note text would be wrong in the other
direction, changing the hash for edits past the truncation point that alter
nothing on screen.

**Behaviour**: equal fingerprint → `204 No Content`, htmx performs no swap.
Different → normal `200` with the rendered partial.

## 5. Density preference

| Key | Store | Values | Default |
|---|---|---|---|
| `FEED_DENSITY` | `engine/settings.py` `get`/`set` | `"compact"`, `"comfortable"` | `"compact"` |

Rendered as `data-density` on the feed region so both densities are one template
and one set of CSS rules. Compact is one line per job (SC-012).

## 6. Theme (existing, newly transmitted)

| Key | Store | Values | Meaning |
|---|---|---|---|
| `THEME` | `engine/settings.py` | `"light"`, `"dark"`, `""` | `""` = no explicit choice; defer to the OS |

Already normalised by `web/main.py:112-119`. New in this feature: the value is
also sent to the browser panel as an additive field (see
`contracts/panel-theme.md`).
