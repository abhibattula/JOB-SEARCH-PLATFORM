# Phase 0 Research — 022 The Case File

Every decision below was checked against the running code or the network on
2026-08-03, not assumed. Three of them changed the design.

## R1 — Which typefaces, from where, at what cost

**Decision**: Vendor **Archivo Variable** (weight 100–900 + width 62–125, one
family) and **IBM Plex Mono** at 400/600, latin + latin-ext subsets, as `.woff2`
under `web/static/fonts/`, with their OFL licence files beside them.

**Measured** (fetched with a woff2-capable user agent, 2026-08-03):

| Family | Files | Size |
|---|---|---|
| Archivo Variable (wdth,wght) | 2 (latin, latin-ext) | **172.2 KB** |
| IBM Plex Mono 400 + 600 | 4 (latin, latin-ext × 2 weights) | **56.6 KB** |
| **Total** | 6 | **~229 KB** |

**Rationale**: 229 KB against a 1.5 GB installer is free. Archivo's width axis
means one family serves both the display role (expanded 700, tight tracking, for
tab labels and page titles) and the body role (regular 400) — a genuine pairing
without a second family. `packaging/jobengine.spec:16` already ships all of
`web/static`, so no packaging change is needed.

**Alternatives rejected**:
- *System fonts only* — zero cost, zero personality; leaves the product looking
  like an internal tool, which is the complaint.
- *Inter* — the single most-used UI face in current software; it would make the
  redesign read as templated.
- *A high-contrast display serif on cream* — this is one of the three looks
  generated design currently defaults to. Rejected on principle: it would appear
  regardless of subject, and this product is not a magazine.

**Risk**: fonts are fetched once during implementation and committed. The built
application never reaches a network for them — verified by a test asserting no
external URL appears in any CSS or template.

## R2 — What the three provenance values actually are

**Decision**: provenance is `match_json.method`, with exactly four states.

| Value | Written at | Stamp |
|---|---|---|
| `"basic"` | `engine/pipeline.py:270` | pencil — dashed ring |
| `"local"` | `engine/upgrade.py:288` (`tier != "cloud"`) | ink — solid ring |
| `"llm"` | `engine/upgrade.py:288` (`tier == "cloud"`) | sealed — double ring |
| absent / no match row | — | explicit "not scored yet" |

**This corrected the design.** The design record said the third state was
"cloud"; the value actually stored is **`"llm"`**. `scoring_tier()` returns
`"cloud"`, and `upgrade.py:288` maps that to `method = "llm"` before storing.
Reading the tier name into the template would have produced a stamp that never
rendered.

`engine/db.py:635` surfaces it to the feed as
`json_extract(j.match_json, '$.method') AS match_method`, so both the feed and
the job page already have it — no query change is needed.

## R3 — How the browser panel learns the theme

**Decision**: add an additive `theme` field to the `overlay_state` and
`watch_start` outbound messages; the panel falls back to
`prefers-color-scheme` when the field is absent or empty.

**Verified**:
- `ext_protocol.outbound(type_, **payload)` (`ext_protocol.py:362-368`) merges
  arbitrary payload into `{v, type, seq, …}`. Outbound messages are plain dicts
  with **no pydantic model**, so adding a field requires no schema change and
  **`PROTOCOL_V` stays 1**.
- `overlay_state` is already sent at `ext_backend.py:403, 479, 494, 510` and
  already handled by the content script (`main.js:240`), as is `watch_start`.
- The theme source is `settings.get("THEME")`, which `web/main.py:112-119`
  normalises to `"light"`, `"dark"` or `""` — `""` meaning "no explicit choice",
  which is exactly the signal the panel needs to defer to the OS.

**Alternatives rejected**:
- *A new message type* — a wholly new type is a larger compatibility surface
  than a field older companions simply ignore.
- *`chrome.storage.local` written by the popup* — needs a second sync path and
  would drift whenever the app's theme changed while the popup was closed.

## R4 — Stopping the feed from rebuilding itself

**Decision**: `feed_partial` computes a fingerprint over the ordered rendered
row data plus the paging context, and returns **`204 No Content`** when it
matches what the client last received. htmx performs no swap on a 204, so the
DOM is left entirely alone.

**Fingerprint input**: for each row in order — id, status, stage, match_score,
match_method, is_new, delisted, follow_up, whether notes are present — plus
`total`, `page`, and the query signature. Anything the applicant can *see*
changing is in the hash; anything they cannot is not.

**Rationale**: the alternative — DOM morphing — would need a morph library
(a JS dependency the constitution's fixed stack forbids) or hand-written diffing
(a large amount of new, hard-to-test code). Not sending unchanged HTML is
strictly simpler and fixes the cause rather than the symptom.

**Preserved**: `pollingAllowed()` (`app.js:144`) keeps suppressing refresh while
the applicant is mid-edit. The 204 path is additional, not a replacement.

## R5 — Verifying contrast without adding a dependency

**Decision**: implement WCAG 2.1 relative luminance and contrast ratio directly
in `tests/test_design_system.py` (about fifteen lines: sRGB → linear, luminance,
`(L1 + 0.05) / (L2 + 0.05)`), parse the token block out of the stylesheet, and
assert every declared foreground/background pairing reaches AA.

**Rationale**: Principle II ($0) and the fixed stack both discourage a new
dependency for arithmetic this small. It also keeps the check honest — the test
reads the *actual* token values from the stylesheet rather than a copy.

## R6 — PDF typography without breaking Unicode coverage

**Decision**: register Archivo (TTF, not woff2 — fpdf2 embeds TrueType) for
headings and the applicant's name, keep DejaVu for body, and register DejaVu via
`set_fallback_fonts()` so any glyph Archivo lacks still renders.

**Verified**: `requirements.txt:42` pins `fpdf2==2.8.7`;
`set_fallback_fonts()` has existed since 2.7.0. The current module already
bundles DejaVu at `assets/fonts/` precisely because "fpdf2's core fonts are
Latin-1 only — resume text routinely has en-dashes/accents"
(`engine/resume_pdf.py:1-11`), so that coverage must not be lost.

**Hard constraint restated**: ATS-safety is not negotiable. Single column,
selectable text, no tables, no images, no repeating header region. The change is
type and spacing only.

## R7 — Feed density

**Decision**: store as `settings.get("FEED_DENSITY")` with default `"compact"`,
using the existing generic store (`engine/settings.py:44,54` — `get(name,
default)` / `set(name, value)`). Rendered as a `data-density` attribute on the
feed region so the entire density change is CSS, not a second template.

**Rationale**: one template, two stylesheets' worth of rules, no duplicated
markup to drift. Compact stays one line per job, which is what protects SC-012.

## R8 — Reduced motion

**Decision**: one global `@media (prefers-reduced-motion: reduce)` block that
neutralises animation and transition across the board, *in addition to* keeping
the existing per-site gating.

**Found while checking**: `styles.css:475-479` transitions `button` and
`.feed tr` with no reduced-motion gate at all, and the View Transitions block at
`:482` gates only the `no-preference` direction. A single global override closes
both without needing every future rule to remember.

## R9 — What must not move

Checked and confirmed still required, so the rewrite is bounded by them:

- prose links keep a non-colour cue — `test_web.py:100`
- banners render server-side, no CLS — `test_web.py:77`
- static assets stay version-stamped — `test_web.py:178`
- command palette present and keyboard-reachable — `test_web.py:64`
- form controls keep accessible labels — `test_web.py:88`
- both fill paths stated honestly — `test_web.py:194`
- companion wizard `ok`/`bad`/`warn` stay visually distinct — `styles.css:386`
  (a version-skew warning must never read as success)
- panel offsets stay `!important`, drag and clamping unchanged — `panel.js:156`

## R10 — A defect found during research, not planned for

`styles.css:557-565` styles the sticky Apply Assist control bar with
`background: var(--bg, #fff)` and `border-bottom: 1px solid var(--border,
#e3e3e3)`. **Neither `--bg` nor `--border` is defined anywhere in the token
block**, so both always fall through to their hardcoded fallbacks. The control
bar has rendered white-on-white in dark mode since feature 017 shipped.

Folded into FR-014 rather than deferred, because the tokens it needs are being
written anyway.
