# Changelog

Every released version, newest first. Dates are the tag dates.

Releases from v0.6.0 onward map one-to-one to a feature folder under
[`specs/`](specs/), which holds the full requirement → design → task history.
The in-app **What's New** overlay carries a plain-language subset of each
entry; this file is the fuller record.

Entries for v1.9.1 and earlier are summarised from their feature names and
release notes. v2.0.0 onward are written from the work itself.

---

## v2.2.0 — The Case File · 2026-08-03

A visual redesign that began as an audit rather than a restyle. The audit
found that **roughly 35 CSS class names were used in the pages and defined in
no stylesheet** — including the entire Apply Assist review list, the screen
read *during* a live employer application. `.grid-2` was used five times on
Profile and defined nowhere, so its ~50 fields had never once rendered in the
two columns the markup asked for.

### A score now shows how it was produced

Every match score renders as a stamp whose **ring** states its provenance:

| Ring | Meaning |
|---|---|
| dashed | keyword match — a guess |
| solid | scored by the offline model on this computer |
| double | full analysis |
| dotted, empty | not scored yet |

Previously a `~` or `•` prefix visible only on hover. Colour is never the only
signal, so it survives greyscale and colour-blindness, and the provenance is
exposed as text to screen readers. The same stamp appears in the feed, on the
job page, on the home strip and in the browser panel, so one job can never
look like two different things.

This also ended a live overclaim: the badge on a posting you browse has
**always** been a keyword guess, but rendered in confident colour bands that
read like a real assessment.

### Measured changes

| | before | after |
|---|---|---|
| Feed rebuilds while idle | 12/min | **0** |
| Jobs visible per screen (1366×768) | 6 | **13** |
| CSS classes used but undefined | ~35 | **0** |
| Navigation height | 45.4px | 39.2px |

### Added

- Two-tier navigation — **Search · Pipeline · Apply · Setup** — with that
  section's views on a second row. Never wraps; both tiers marked current.
- Profile **section index with live per-section counts**. A blank field here
  is a field Apply Assist must hand back to you on an employer's form, so
  "Contact & address 0/10" says where the next application will stall. Counts
  update as you type; a save bar appears only once something changed.
- Feed **density** control (Compact / Comfortable), remembered.
- The home dashboard can be **hidden**, with a link always back.
- Two bundled typefaces (Archivo, IBM Plex Mono), ~229 KB, shipped in the
  installer. No font is ever fetched from a network.

### Changed

- The feed sends `204 No Content` when nothing changed, so htmx performs no
  swap and scroll position, hover and focus survive a poll.
- The home dashboard's three tall cards became one strip with the same
  information.
- The browser panel uses the app's tokens and follows your light/dark choice.
  Delivered as an **additive** protocol field — `PROTOCOL_V` stays 1, and an
  older companion simply ignores it.
- Resume and cover-letter PDFs gained real typographic hierarchy. **ATS-safety
  is unchanged**: single column, selectable text, no tables, no images, no
  repeating headers. DejaVu is registered as an fpdf2 *fallback* so Unicode
  coverage survives the font change.
- Motion is keyframes and transforms only. Windows renders in WebView2
  (Chromium) and macOS in WKWebView (WebKit); Chromium-only scroll-driven
  animation would have given one build motion and the other silence. A test
  fails the build if it appears.

### Fixed

- The Apply Assist sticky control bar had rendered **white in dark mode since
  v1.7.0** — it referenced `--bg` and `--border`, defined nowhere.
- Every feed load raised a spurious "Saved" notification.
- The What's New panel filled the entire viewport on a new version, so a fresh
  install showed no jobs until it was dismissed twice.
- Reduced-motion is now honoured everywhere, including places that ignored it.

### Verification

2196 unit tests · 109 real-browser tests on Windows **and** macOS · secret
hygiene · frozen-build smoke · both installers verified by magic bytes and
SHA-256.

The browser suite caught a `ReferenceError` that **2184 unit tests missed**:
`main.js` handles `message`, a new line said `msg.theme`, and one error in a
content script kills the whole companion — 14 tests timed out with no error
text. `node --check` passed the file. Syntax validity is not reference
validity; there is now a test for exactly this.

---

## v2.1.0 — The Real Application · 2026-08-03

Fixed a real Intel Workday run that reported **Filled 5 · Needs you 149 · Seen
156**, mostly blank rows and the same question repeated.

- **The 149-row flood, at three source-level causes**: rows were de-duplicated
  by element rather than by question (a Workday dropdown is a button *plus* a
  listbox, so every one produced two rows); a whitespace-only label passed as
  a question; and the field index was never pruned, so every wizard step and
  React remount accumulated forever.
- **Work history and education fill themselves.** The resume had already been
  parsed into employers, titles, dates, schools, degrees and GPA, and the fill
  layer had never once read it. Fewer entries than the form has blocks leaves
  the extras for you rather than filling from the wrong job.
- **Answers you type are learned**, on a Learned answers page you can edit or
  wipe. Passwords, self-identification, date of birth, government ID and bank
  details are refused before the value is copied anywhere.
- **The free cloud AI tier became reachable** — it was switched off in a way
  nobody could find, so saving a key changed nothing.
- **Tailoring stopped failing silently** (the error handler crashed on an empty
  response) and no longer queues behind background scoring.
- Draggable Apply Assist panel, page reports, five more free job boards, and
  new profile fields real applications kept asking for.

---

## v2.0.0 — Every Job Ranked · 2026-08-02

Scoring split into instant keyword ranking for **every** job plus a
single-flight background AI pass that yields to Apply Assist. Refresh stopped
holding itself open. Rich-text cover letters fill.

---

## v1.9.0 / v1.9.1 — Door to Door · 2026-07-31

Progression clicks: opening an application, advancing a completed wizard step,
and signing in immediately after the engine filled saved credentials. The
final Submit is always yours.

## v1.8.0 — The Companion · 2026-07-29

The on-page companion widget made real, with real-browser interaction coverage
as a definition of done.

## v1.7.0 — The Truthful Fill · 2026-07-29

Stopped filling the wrong things — most notably never substituting your legal
name for a preferred name.

## v1.6.0 — The Fill Release · 2026-07-27

Made filling work end to end on the page: choice-aware answers, on-page
review, and containment of the AI runtime.

## v1.5.0 — The Pairing Release · 2026-07-25

Fixed pairing and connection between the app and the browser companion.

## v1.4.0 — The Experience Release · 2026-07-24

Shared elevation and motion, skeletons, and the command palette.

## v1.3.0 — Refinements · 2026-07-24

Sort affordances, the job-detail back control, and date rendering.

## v1.2.0 — Discovery Copilot · 2026-07-24

A local-only, read-only match and sponsorship badge on postings you browse.

## v1.1.0 — Coverage Release · 2026-07-24

Wider field coverage for Apply Assist.

## v1.0.0 / v1.0.1 — Copilot Release · 2026-07-23

The home dashboard, AI draft review, and the companion connection card.

## v0.9.0 — Live Fill Engine · 2026-07-23

The live watch feed and on-page fill engine.

## v0.8.0 — Launch Release · 2026-07-22

The desktop shell: in-app updates, clipboard and external-link paths that work
inside WebView2, and the 14-day default feed window.

## v0.7.0 — Moat Release · 2026-07-22

The "Instrument" design system, the pipeline board, the resume builder and
Apply Assist mission control.

## v0.6.0 / v0.6.1 — Profile overhaul · 2026-07-21

## v0.3.0 → v0.5.6 · 2026-07-20 → 2026-07-21

The first five features, released across eleven tags (v0.3.0, v0.4.0–v0.4.2,
v0.5.0–v0.5.6 — the tag history begins at v0.3.0): ingestion from public job
APIs, sponsorship
intelligence from USCIS/DOL records, resume matching, the feed, and the first
Apply Assist. Grouped rather than itemised — these predate the per-release
notes, and inventing detail for them would be worse than pointing at the
record. See [`specs/001-ai-job-engine/`](specs/) through
[`specs/005-apply-assist/`](specs/) for the full history.

Notable within them: v0.4.0 shipped a frozen build whose bundled `jobspy` DLL
failed silently and reported `found=0` rather than an error — the reason
`packaging/smoke_test.py` now gates every release.
