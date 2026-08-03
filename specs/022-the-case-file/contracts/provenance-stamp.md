# Contract — The provenance stamp

**The signature element.** One component, three sizes, four surfaces.
**Consumers**: feed, job detail, dashboard, browser panel.

## Input

Exactly one value: `match_method` from `match_json.method`
(`engine/db.py:635`). Verified values (R2):

| Value | Written at |
|---|---|
| `"basic"` | `engine/pipeline.py:270` |
| `"local"` | `engine/upgrade.py:288` when tier ≠ cloud |
| `"llm"` | `engine/upgrade.py:288` when tier = cloud |
| absent / no match row | — |

**The treatment is a pure function of this value.** No surface may derive it
from anything else — that is what keeps the four surfaces from disagreeing.

## Output

| Provenance | Ring | Colour | Numeral | Accessible text |
|---|---|---|---|---|
| `basic` | dashed | `--pencil` | mono, `--pencil` | "keyword match" |
| `local` | solid | `--ink` | mono, `--ink` | "scored on this computer" |
| `llm` | double | `--seal` | mono, `--seal` | "full analysis" |
| absent | dotted, empty | `--ink-soft` | "—" | "not scored yet" |

**Colour is never the only differentiator** (FR-016): ring style carries the
same information, so the stamp survives greyscale and colour-blindness.

## Sizes

| Size | Where | Diameter |
|---|---|---|
| `sm` | feed match cell, dashboard row | ~28px |
| `lg` | job detail analysis column | ~72px |
| `panel` | browser panel score circle | ~46px (matches today's) |

## Accessibility

- The numeral is the accessible name; the provenance phrase is exposed as
  additional text (visually hidden at `sm`), not as a `title` alone (FR-017).
- The existing explanatory `title` is **kept**, not replaced — it still says what
  to do about a basic score ("add an AI key in Settings").
- No animation on the stamp. It is a status, not an event.

## Test assertions

| # | Assertion |
|---|---|
| S1 | Each of the four provenance values renders a distinct, non-colour differentiator |
| S2 | The provenance phrase is present as text for every value |
| S3 | Feed, job detail, dashboard and panel produce the same treatment for the same value |
| S4 | A job with no match row renders the unscored state, never an empty stamp |
| S5 | The existing explanatory tooltip text survives for `basic` and `local` |
