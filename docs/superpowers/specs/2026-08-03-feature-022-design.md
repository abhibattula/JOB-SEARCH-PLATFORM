# Feature 022 — "The Case File" (v2.2.0)

**Date:** 2026-08-03 · **Status:** approved plan (plan mode, 2026-08-03); this
doc is the durable design record and the seed for `/speckit-specify`.
**Prior:** 021 "The Real Application" (v2.1.0) made Apply Assist tell the truth
about a real Workday form. This release makes the whole product *look* like it
means it — and repairs the surfaces that were never styled at all.

**Held gate:** the applicant asked that no version be created or pushed until
they approve the design. Phase 1 stops after the Feed for exactly that. No tag,
no release, no push until they say go.

## 1. Problem

The applicant's request: *"can we do a full visual redesign into a more
interactive smooth and make it more user friendly … check where can I do
improvements etc."*

The last clause is the one that mattered. A taste-only redesign would have
missed the actual finding: **large parts of the interface have no styling at
all.** The app is not ugly by choice; it is unfinished in places nobody looked.

## 2. Audit findings (2026-08-03, file:line verified)

**F1 — ~35 CSS classes are used in markup and defined in no stylesheet.**
Measured by extracting every `class="…"` token across `web/templates/**` and
differencing against every selector in `web/static/styles.css` (the only
stylesheet; `web/static/` contains just `app.js`, `htmx.min.js`, `palette.js`,
`styles.css`, `favicon.ico`). After discarding Jinja-expression fragments the
survivors include:

- `.grid-2` ×5 (`profile.html:54,103,157,203,272`) — the five "two-column"
  sections are plain `<div>`s, so ~50 profile fields render as one stacked
  column.
- `.hint` ×18 — every field hint is visually identical to body text.
- `.switch` (`settings.html:186`) — the escort toggle is a bare browser
  checkbox, not a switch.
- The entire Apply Assist review vocabulary: `.answers-review`, `.answer-list`,
  `.answer-item`, `.q`, `.why`, `.answer-capture`, `.fill-coverage`,
  `.activity-log`, `.autofill-active`, `.fill-where`, `.fill-where-warning`
  (`partials/autofill_status.html`). **The screen used during a live
  application is unstyled markup.**
- `.board-followup`, `.fu-date`, `.fu-notes`, `.fu-save`
  (`partials/pipeline_board.html`); `.import-decision`
  (`partials/import_review.html`); `.answer-bank-delete`, `.eeo-answer-input`,
  `.reset-learned` (`partials/profile_answer_bank.html`); `.job-url`, `.jd`
  (`job_detail.html:39,42`); `.lead` (`companion.html:18,22`); `.export-link`
  (`feed.html:68,69`); `.autofill-page`, `.autofill-job-check`
  (`autofill.html`); `.pager` (`partials/feed_table.html:107`).

Some names ride on a styled base and are harmless (`error-banner stamp-problem`,
`mission-panel whats-new`, `pager settings-actions`). The list above is the set
that carries layout or emphasis and gets none.

**F2 — the extension panel is a second, unrelated design system.**
`extension/content/panel.js:255-360` hardcodes GitHub-dark hex — `#0d1117`
surface, `#238636` primary button, `#3fb950` status dot, `#58a6ff` link,
`#30363d` border — inside a shadow root opened with `all:initial`
(`panel.js:183`). It shares no token with the app and cannot follow the
light/dark choice. This is the surface where the actual application happens.

**F3 — `.skeleton` is dead.** Built in feature 014 with a shimmer keyframe
(`styles.css:491-498`) and referenced by no template and no JS. Async surfaces
(next actions, AI scoring, first feed paint) pop in with a layout jump instead.

**F4 — `.grouplabel` never renders.** Styled at `styles.css:141`; the nav marks
its four groups with `aria-label` only (`base.html:20,26,32,37`). The result is
14 flat links in one `flex-wrap` bar that wraps to two rows on a laptop.

**F5 — the feed destroys and rebuilds its table every 5 seconds.**
`feed.html:73-78`: `hx-trigger="every 5s [pollingAllowed()]"` with
`hx-swap="innerHTML"` over the whole `#feed-region`. `pollingAllowed()`
(`app.js:144`) only pauses for a focused input or an open notes `<details>` —
so while the applicant is simply *reading* the feed, the table is replaced 12
times a minute, resetting hover, focus and any in-flight transition. This is
the largest single source of "not smooth", and it is a server-side problem, not
an animation problem.

**F6 — monospace has been diluted until it signals nothing.** `--mono` is
applied to nav group labels, section headings, toasts, the footer, badges,
chips, buttons and the brand as well as to data. The one genuinely good idea in
the existing design — *monospace means machine-truth* — no longer reads.

## 3. Locked decisions (AskUserQuestion, 2026-08-03)

| # | Question | Answer |
|---|---|---|
| D1 | How far from the current look? | **The Case File** — keep mono-as-machine-truth, rebuild around it |
| D2 | What replaces the 14-link bar? | **Two-tier tabs** — four stable tabs, current tab's views below |
| D3 | Which surfaces? | **All nine app screens + the extension panel + the generated PDFs** |

D3 explicitly did **not** select "dark mode as a first-class pass". Dark stays a
derived token remap — kept working and verified in the visual pass, but not
separately art-directed.

**Out of scope:** `practice_apply.html`, `practice_posting.html`,
`practice_frame.html`. They deliberately imitate Greenhouse/Workday markup
(`.select__control`, `.rs__singleValue`, their own inline `<style>` blocks) and
are the fixtures `test_web.py:302,318` assert against. Restyling them would
invalidate what they test.

## 4. Design

### 4.1 Color — ink, pencil, flag, seal

Nine tokens named for what they *mean* in this product rather than for hue.
Every value lives in the token block; no component uses a raw hex.

| Token | Light | Meaning |
|---|---|---|
| `--paper` | `#f6f7f5` | page |
| `--leaf` | `#ffffff` | card / raised surface |
| `--ink` | `#12211c` | text, and **a fact the applicant confirmed** |
| `--ink-soft` | `#4a5b53` | secondary text |
| `--rule` | `#dfe4e0` | hairlines, dividers |
| `--seal` | `#1f6f5c` | action, current, done |
| `--pencil` | `#4a5f7a` | **provisional — drafted, not confirmed** |
| `--flag` | `#b8792a` | **needs the applicant** |
| `--stop` | `#a63a2e` | rejected, failed, destructive |

Each gets a `-tint` companion. The dark theme remaps the same nine names
(graphite paper, the seal lifting to a phosphor teal). The existing
`[data-theme]` + `prefers-color-scheme` cascade at `styles.css:70-119` is kept
structurally intact — only its values change — because it already gets the hard
part right: an explicit choice wins, the OS preference decides only when no
choice is set.

The semantic pairing is the point, and it is already how the product behaves:

> **ink = you confirmed it · pencil = the AI drafted it · flag = it needs you ·
> seal = it is done.**

Today those are four unrelated colors (purple `--draft`, amber `--warn`, green
`--ok`, blue `--accent`) that have to be relearned per screen.

### 4.2 Type — two files, three roles

Bundled at `web/static/fonts/`. No CDN, no build step; the offline and $0
constraints hold unchanged. `packaging/jobengine.spec:16` already ships all of
`web/static`, so the installer picks the files up with no packaging change.

- **Archivo Variable** (weight + width axes, one woff2) — display at expanded
  700 with tight tracking for tab labels and page titles; regular 400 for body.
  One file covering two roles.
- **IBM Plex Mono Variable** — **data only**: scores, ids, dates, counts,
  versions, paths, field names. Nowhere else. This is F6's repair.

System fallbacks stay in each stack so a missing font degrades rather than
breaks. OFL license files ship beside the fonts.

Deliberately *not* a high-contrast display serif on cream: that is the current
default look of generated design, and it says nothing about this product.

### 4.3 Signature — the provenance stamp

The one element the product is remembered by. **A match score renders
differently depending on how it was produced.**

| Today | Becomes |
|---|---|
| `~72` + a `title` tooltip | **pencil stamp** — dashed ring, `--pencil` — keyword guess |
| `•72` + a `title` tooltip | **ink stamp** — solid ring, `--ink` — scored on-device |
| `72` + a `title` tooltip | **sealed stamp** — double ring, `--seal` — full cloud analysis |

The data already exists: `job.match_method` is `basic` / `local` / else, and is
currently expressed as a one-character prefix plus a hover tooltip
(`partials/feed_table.html:63-67`, `job_detail.html:85-93`). Provenance is
invisible unless you hover, on the number the applicant makes decisions with.

Making it visual is on-brief rather than decorative: never presenting a guess as
a fact is this product's central commitment (the 017 "preferred name" lesson,
the 021 never-invent rule). The stamp renders at three sizes — inline in the
feed's match cell, large on the job page, and as the score circle in the
extension panel — which is what ties app and panel into one product.

The same vocabulary extends to Apply Assist with no new concepts — because
**the protocol already encodes it**: `FillItem.flag` is
`Literal["ai_draft", "needs_you"] | None` (`ext_protocol.py:348`). A field
filled from the profile is **ink** (no flag), an AI draft awaiting review is
**pencil** (`ai_draft`), a field needing the applicant is **flagged**
(`needs_you`). The design is not inventing a semantics; it is giving the one
the engine already speaks a visual form.

The container asking for review is flagged; the provisional text inside it is
pencil. That is a better hierarchy than today, where drafts shout in purple and
the thing actually needing a human does not.

### 4.4 Structure — index tabs

Four tabs (Search · Pipeline · Apply · Setup) over a second row carrying that
tab's views. The four groups already exist in `base.html:20-41` as `aria-label`s
— this makes them visible rather than inventing structure, and it is F4's
repair. The active tab drops its bottom rule and merges into the page surface: a
literal file tab. The top row can never wrap; the second row scrolls
horizontally when narrow.

`aria-current="page"` stays on the active view link, and the tab row gets
`aria-current` on the active tab, so the existing accessibility contract holds.

### 4.5 Motion — "the file settles"

One system. Every use site gated on `prefers-reduced-motion`, including the ones
currently ungated (`styles.css:475-479` transitions `button` and `.feed tr`
unconditionally).

- Rows and cards enter with a 6px rise + fade, staggered ~20ms, capped at ~12
  elements so a 100-row feed does not cascade for two seconds.
- View Transitions (already enabled, `styles.css:482-488`) refined to a
  directional slide matching tab order.
- **`.skeleton` finally used** (F3) on genuinely async surfaces: next actions,
  the AI-scoring channel, the feed's first paint.
- **F5 is fixed at the source, not animated over.** `feed_partial`
  (`web/main.py:705-728`) computes a fingerprint over the rendered row data and
  returns `204 No Content` when nothing changed; htmx leaves the DOM untouched.
  Scroll, hover and focus survive a poll. `pollingAllowed()` stays as the
  mid-edit guard it already is.

### 4.6 Per-surface changes

**Feed** — rows become records: role and company lead, the stamp sits right,
sponsorship and grade as quiet marks. Below ~900px the table becomes stacked
record cards; today a 7–9 column table has no responsive fallback at all.
A comfortable/compact density toggle, persisted through the generic
`settings.get()` / `settings.set()` store (`engine/settings.py:44,54`), for
scanning hundreds of jobs.

**Job detail** — the large stamp anchors the analysis column; `.jd` and
`.job-url` get real treatment; tailored output renders in pencil until accepted.

**Profile** — `.grid-2` and `.hint` become real, so ~50 fields lay out in two
columns with distinguishable hints. A sticky section index (Basic · Contact ·
Work authorization · History · Education · Answers) makes it navigable instead
of one long scroll. The `id="field-*"` anchors added in 021 for the panel's
"add it to your profile" deep links are preserved.

**Settings** — a real `.switch`; the 021 AI-tier choice gets the weight it
deserves; same section index treatment.

**Apply Assist** (`autofill.html` + `partials/autofill_status.html`) — the
largest single repair. The whole F1 review vocabulary is built for the first
time, and filled/drafted/needs-you become ink/pencil/flag. The sticky controls
from 017 (`styles.css:557-565`) are kept — that fix stays, and its hardcoded
`var(--bg, #fff)` / `var(--border, #e3e3e3)` fallbacks (which reference tokens
that do not exist) get corrected to real ones.

**Companion · Diagnostics · Analytics · Learned answers** — remaining F1 classes
built. `.chart-svg` already reads from variables (`styles.css:534-552`), so the
charts re-token for free. The 019 companion wizard `ok`/`bad`/`warn` step states
(`styles.css:386-394`) keep their distinct treatments — a version-skew warning
must never read as success.

**Extension panel** (`extension/content/panel.js`) — the F2 hex block is
replaced by the same nine tokens, **injected into the shadow root** since
`all:initial` blocks inheritance. Theme arrives over the existing bridge as an
**additive** field on an outbound envelope — `outbound()` already merges
arbitrary payload into `{v, type, seq, …}` (`ext_protocol.py:362-368`), and a
companion that does not know the field ignores it — with `prefers-color-scheme`
as the fallback. **`PROTOCOL_V` stays 1.** Every position offset stays
`!important`: that is the v1.0.0–v1.7.0 bug documented at `panel.js:156`, and
the 021 drag work depends on it.

**PDFs** (`engine/resume_pdf.py`) — hierarchy, spacing and section rules
reworked; the app's face used for headings with **DejaVu registered as an fpdf2
fallback** (`requirements.txt:42` pins `fpdf2==2.8.7`, which has
`set_fallback_fonts()`), preserving the Unicode coverage the module docstring
depends on. **ATS-safety is a hard constraint, not a preference:** single
column, selectable text, no tables, no graphics, no header/footer regions. The
redesign is typographic only.

## 5. Guardrails

$0 recurring cost · works offline with no key · `engine/` never imports `web/` ·
no JS framework, no Node build step, no CDN · secrets stay fill-and-forget and
never render in a report, log or diagnostic · `PROTOCOL_V` stays 1 · the human
always presses the final Submit / Create account / pay · CAPTCHA is never
interacted with · nothing is ever clicked on LinkedIn.

Plus the invariants the existing suite asserts, which are design requirements in
their own right and must survive the rewrite:

| Invariant | Asserted by |
|---|---|
| prose links keep a non-color cue (WCAG 1.4.1) | `test_web.py:100` |
| banners render server-side, not load-injected (no CLS) | `test_web.py:77` |
| static assets stay cached and version-stamped | `test_web.py:178` |
| the command palette stays present and accessible | `test_web.py:64` |
| form controls keep accessible labels | `test_web.py:88` |
| both fill paths are stated honestly | `test_web.py:194` |

`test_api.py` (77 markup references), `test_routes_autofill.py` (24) and the
browser suite `tests/integration/test_companion_widget.py` (24) are the other
markup-coupled surfaces; each assertion that breaks must be re-read to decide
whether the *test* or the *markup* was right, never blanket-updated.

## 6. Non-goals

A new information architecture beyond the tab grouping · any change to what the
engine ingests, scores or fills · restyling the practice sandbox · a dark-mode
art-direction pass (D3 declined it) · multi-column or graphical PDFs · webfont
loading from any network · a CSS framework or preprocessor · store publication ·
code signing.

## 7. Success criteria

1. **Zero undefined classes.** Every class used in a template resolves to a
   selector in the stylesheet — enforced as a test, not a review habit.
2. **One design system.** No raw hex outside the token block, in the app *or*
   the panel; the panel follows the applicant's light/dark choice.
3. **The feed is quiet when idle.** No DOM replacement occurs while content is
   unchanged; scroll position and hover survive a poll cycle.
4. **Provenance is legible without hovering** at every place a score appears.
5. **Nothing regresses**: full unit battery ×2, `-m browser` on Windows *and*
   macOS, secret hygiene, frozen smoke — all green before the gate is offered.
6. **No version exists** until the applicant approves what they see.

## 8. Verification

**New — `tests/test_design_system.py`.** The audit that produced §2 becomes the
regression gate:

- every class used in `web/templates/**` is defined in `web/static/styles.css`
  (the test that would have caught all ~35 in F1)
- no raw hex outside the `:root` / `[data-theme]` token blocks, in the
  stylesheet or in `extension/content/panel.js`
- no external URL in any CSS or template; every `@font-face` src resolves to a
  file that exists on disk
- every foreground/background token pair meets WCAG AA in **both** themes

**Existing gates.** Full unit battery ×2 → `-m browser` on Windows **and**
macOS → secret hygiene → frozen smoke on the packaged build. 020's tag had to be
cut twice because macOS caught two bugs Windows passed; that is a gate, not a
note.

**Visual pass.** Run the app and walk all nine screens in light and dark, the
panel on a real application page, and both generated PDFs.

**Behavioural check.** Confirm the 204 path fires when the feed is unchanged and
that scroll and hover survive a poll.

## 9. Process

1. Branch `022-the-case-file`; speckit chain (specify → clarify → plan →
   checklist → tasks → analyze); resolve every analysis finding before code.
2. **Phase 1 — tokens, fonts, tab nav, Feed only. Then stop.** Show the Feed in
   light and dark and the stamp at all three provenance levels. **The applicant
   approves or redirects before anything else is touched.**
3. Phases 2–5 on approval: remaining app screens → Apply Assist → extension
   panel → PDFs. Hybrid `/speckit-implement` + superpowers TDD throughout,
   red→green per task.
4. Docs updated (`USER_MANUAL`, `USER_GUIDE`, `README`, `WHATS_NEW`), both
   platform suites, frozen smoke.
5. **Held: no tag, no release, no push of a version until the applicant says
   go.** v2.2.0 is cut only on their word.

## 10. Still outstanding from 019/021 (the applicant's, unchanged by this)

Press "Save page report" on the real Intel Workday application (T012) · re-run
Apply Assist there and record filled/needs-you/seen against 5/149/156 (T047) ·
time one tailoring request per tier with a Groq key saved (T061) · 019's T076 —
install, press ↻ at `chrome://extensions`, save a Workday login, escort to
Review, confirm Submit is never pressed.
