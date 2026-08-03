# Design & Accessibility Checklist: The Case File

**Purpose**: Everything about this feature that a passing test cannot judge, plus the accessibility floor the redesign must not fall through.
**Created**: 2026-08-03
**Feature**: [spec.md](../spec.md) · [design record](../../../docs/superpowers/specs/2026-08-03-feature-022-design.md)

## Completeness — nothing renders as a fallback

- [ ] CHK001 Every one of the ~35 previously-undefined classes now has a definition, verified by the mechanical gate, not by eye
- [ ] CHK002 Profile's five `.grid-2` sections render as two columns at 1280px and collapse to one below the breakpoint
- [ ] CHK003 Every `.hint` is distinguishable from its label and from body text at a glance
- [ ] CHK004 The Settings escort control reads as a switch, and its on/off state is obvious without reading the label
- [ ] CHK005 The Apply Assist review list shows question, reason and state as three separable things
- [ ] CHK006 The sticky Apply Assist control bar is legible in dark mode (the `--bg`/`--border` defect, R10)
- [ ] CHK007 No screen shows a default browser control that the design intended to style
- [ ] CHK008 The three practice-sandbox pages are byte-identical to before this feature

## Provenance stamp

- [ ] CHK009 All four states — basic, local, llm, unscored — render distinctly at `sm` size in the feed
- [ ] CHK010 The stamp is still legible at `sm` on a 1366×768 laptop screen
- [ ] CHK011 The four states remain distinguishable with colour removed (greyscale screenshot check)
- [ ] CHK012 Feed, job detail, dashboard and panel show the same treatment for the same value — checked side by side, not assumed
- [ ] CHK013 The existing explanatory tooltip still tells the applicant what to do about a `basic` score
- [ ] CHK014 The stamp does not animate

## Motion & smoothness

- [ ] CHK015 With the feed open and untouched, `/partials/feed` returns 204 after the first load and the rows are never replaced
- [ ] CHK016 Scroll position survives a full minute of polling
- [ ] CHK017 Hover state on a row survives a poll cycle
- [ ] CHK018 A genuinely new job still appears without a manual refresh
- [ ] CHK019 Editing a note changes the visible summary and the row does refresh (the fingerprint is not presence-only)
- [ ] CHK020 With `prefers-reduced-motion: reduce` set at the OS level, no animation, shimmer, transition or view transition plays anywhere
- [ ] CHK021 Skeleton placeholders reserve the space their content will occupy — no layout shift on arrival
- [ ] CHK022 Refresh is still suppressed while mid-edit in a notes field

## Navigation & layout

- [ ] CHK023 The primary tab row occupies exactly one line at 1280px and at 1024px
- [ ] CHK024 The active tab and the active view are both visibly current, not just one
- [ ] CHK025 The second row scrolls horizontally rather than wrapping when narrow
- [ ] CHK026 The feed becomes stacked records — not a horizontally scrolling table — below the breakpoint
- [ ] CHK027 Compact density shows at least as many jobs per screen as the current build (SC-012 — counted, not estimated)
- [ ] CHK028 Comfortable density is genuinely easier to read, not merely taller
- [ ] CHK029 The density choice survives an app restart
- [ ] CHK030 Every `id="field-*"` anchor the panel deep-links to still resolves after the Profile relayout

## Typography

- [ ] CHK031 Monospace appears **only** on machine-produced values; no heading, label, button or nav item uses it
- [ ] CHK032 Renaming the fonts directory leaves every page usable in the system fallback
- [ ] CHK033 Display and body faces are distinguishable in role, not just size
- [ ] CHK034 No text is clipped or overflows at either density in either theme

## Accessibility floor

- [ ] CHK035 Every token pairing meets WCAG AA in both themes (mechanical, but re-check the ones the test had to skip)
- [ ] CHK036 Keyboard focus is visible on every interactive element, in both themes
- [ ] CHK037 Tab order through the two-tier nav is logical
- [ ] CHK038 The command palette still opens with the keyboard and is operable from it
- [ ] CHK039 Prose links retain a non-colour cue
- [ ] CHK040 Every form control still has an accessible label
- [ ] CHK041 Score provenance is announced as text, not conveyed by colour alone
- [ ] CHK042 The companion wizard's ok / bad / warn states remain visually distinct — a version-skew warning must never read as success

## Extension panel

- [ ] CHK043 App set to light → panel renders light; set to dark → panel renders dark
- [ ] CHK044 Theme unset → panel follows the OS preference
- [ ] CHK045 Changing theme mid-session updates the panel without a reload
- [ ] CHK046 The panel contains no colour literal
- [ ] CHK047 Drag, position persistence and viewport clamping behave exactly as in v2.1.0
- [ ] CHK048 A pre-022 companion connects and fills normally
- [ ] CHK049 `PROTOCOL_V` is still 1
- [ ] CHK050 No message carrying the theme also carries a secret

## Generated PDFs

- [ ] CHK051 Name, section headings and body are distinguishable by size and weight
- [ ] CHK052 Text is fully selectable in a PDF reader
- [ ] CHK053 Layout is a single column with no table, image or repeating header
- [ ] CHK054 A name with accented characters renders — no placeholder glyphs (the DejaVu fallback works)
- [ ] CHK055 Both resume and cover letter are checked, not just the resume

## Regression risk

- [ ] CHK056 Every assertion broken by a rename was re-read individually; none was blanket-updated
- [ ] CHK057 No secret, credential or pairing value became visible through any restyled surface
- [ ] CHK058 `engine/` still imports nothing from `web/`
- [ ] CHK059 No network request is made for any asset — verified with the machine offline
- [ ] CHK060 Frozen build renders correctly, not just the dev server

## The gate

- [ ] CHK061 Phase 1 screenshots sent: Feed, light and dark, all three provenance levels
- [ ] CHK062 Applicant approved or redirected before Phase 2 began
- [ ] CHK063 No tag, no release, no version pushed

## Notes

- Check items off as completed: `[x]`
- CHK011, CHK028 and CHK033 are judgement calls. Record the judgement, not just the tick.
- CHK027 and CHK059 need a real measurement and a real disconnection respectively — an assumption on either is worthless.
